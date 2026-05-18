#!/usr/bin/env bash
# D.14 — Redis down mid-stream.
#
# Brings up redis, kicks off zeek against arp-flood.pcap in the
# background, waits a short delay, kills redis with SIGKILL, lets zeek
# finish, brings redis back up, and asserts:
#
#   D.14a  NO SILENT LOSS. With zeek exiting 0, every ARP frame
#          fired one xAdd. So XLEN_final + xAdd_failed_lines should
#          account for ~all FRAME_COUNT xAdds (1% tolerance). Anything
#          less means writes were silently dropped without the bridge
#          logging them -- which is exactly the "swallowed silently"
#          behavior D.14 is meant to forbid. As of bridge 2f1501f
#          this assertion FAILS (node-redis@4 offlineQueue drops
#          queued commands on quit without rejecting their promises);
#          see send-to-redis.js comment + test-status.md "Bugs surfaced".
#   D.14b  Zeek exited 0 (graceful degradation; no unhandled rejection).
#   D.14c  Final XLEN < FRAME_COUNT (sanity check: kill landed
#          mid-burst, not after Zeek already finished -- guards against
#          orchestration races producing a false PASS on a stale run).
#
# Prerequisites: arp-flood.pcap must exist
# (run fixtures/arp_flood.py from the host).
#
# Usage: run from anywhere; the script normalizes its own cwd.
# Env knobs:
#   KILL_DELAY      seconds to wait before SIGKILL'ing redis (default 0.5)
#   FRAME_COUNT     expected total frames in arp-flood.pcap (default 10000)

set -uo pipefail

KILL_DELAY=${KILL_DELAY:-0.5}
FRAME_COUNT=${FRAME_COUNT:-10000}

cd "$(dirname "$0")/.."
COMPOSE_DIR="$(pwd)"

echo "=== D.14 setup ==="
echo "compose dir: $COMPOSE_DIR"
echo "kill delay:  ${KILL_DELAY}s"
echo "frame count: $FRAME_COUNT"

docker compose down -v >/dev/null 2>&1 || true
docker compose up -d redis
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  sleep 0.1
done
echo "redis ready"

echo
echo "=== launching zeek (background) ==="
LOG=$(mktemp -t d14-zeek-log.XXXXXX)
echo "log: $LOG"

docker compose run --rm -T zeek \
    zeek -r /fixtures/arp-flood.pcap \
    policy/protocols/conn/mac-logging /bridge/send-to-redis.js \
    >"$LOG" 2>&1 &
ZEEK_PID=$!

# Container startup + depends_on:service_healthy takes >>500ms on a
# cold image, so a fixed sleep races and ends up killing redis before
# zeek's depends_on gate has even cleared. Wait for the bridge's
# zeek_init log line, then KILL_DELAY into actual processing.
echo "=== waiting for bridge to connect to redis ==="
CONNECT_TIMEOUT=30
for i in $(seq 1 $((CONNECT_TIMEOUT * 10))); do
  if grep -q "\[bridge\] connected" "$LOG" 2>/dev/null; then
    echo "bridge connected at i=$i (~$((i / 10))s)"
    break
  fi
  sleep 0.1
done

if ! grep -q "\[bridge\] connected" "$LOG" 2>/dev/null; then
  echo "FAIL: bridge did not connect within ${CONNECT_TIMEOUT}s"
  echo "--- log ---"
  cat "$LOG"
  kill "$ZEEK_PID" 2>/dev/null || true
  docker compose down -v >/dev/null 2>&1 || true
  exit 2
fi

echo "=== sleeping ${KILL_DELAY}s into processing, then SIGKILL'ing redis ==="
sleep "$KILL_DELAY"
docker compose kill redis

echo "=== waiting for zeek to finish ==="
wait "$ZEEK_PID"
ZEEK_EXIT=$?
echo "zeek exit code: $ZEEK_EXIT"

echo
echo "=== restarting redis to inspect XLEN ==="
docker compose start redis
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  sleep 0.1
done
FINAL_XLEN=$(docker compose exec -T redis redis-cli XLEN zeek:events | tr -d '\r')
echo "final XLEN: $FINAL_XLEN"

FAIL_COUNT=$(grep -c "\[bridge\] xAdd failed" "$LOG" || true)
echo "[bridge] xAdd failed lines in stderr: $FAIL_COUNT"

echo
echo "=== assertions ==="

PASS=0
FAIL=0

# D.14a: no silent loss. Tolerate up to 1% slack for events that may
# not have fired yet at the moment of the kill (Zeek's pcap-read
# cadence isn't perfectly observable from outside).
TOLERANCE=$((FRAME_COUNT / 100))
ACCOUNTED=$((FAIL_COUNT + FINAL_XLEN))
SILENT_LOSS=$((FRAME_COUNT - ACCOUNTED))
if [ "$ZEEK_EXIT" -ne 0 ]; then
  echo "  D.14a SKIP  zeek didn't finish (exit=$ZEEK_EXIT); accounting not assertable"
elif [ "$SILENT_LOSS" -le "$TOLERANCE" ]; then
  echo "  D.14a PASS  accounted: XLEN=$FINAL_XLEN + failed=$FAIL_COUNT = $ACCOUNTED of $FRAME_COUNT"
  PASS=$((PASS + 1))
else
  echo "  D.14a FAIL  silent loss: $SILENT_LOSS of $FRAME_COUNT dropped without an error log"
  echo "              (XLEN=$FINAL_XLEN + failed-log=$FAIL_COUNT = $ACCOUNTED; tolerance=$TOLERANCE)"
  FAIL=$((FAIL + 1))
fi

if [ "$ZEEK_EXIT" -eq 0 ]; then
  echo "  D.14b PASS  zeek exited cleanly (exit=0)"
  PASS=$((PASS + 1))
else
  echo "  D.14b FAIL  zeek exit code was $ZEEK_EXIT"
  FAIL=$((FAIL + 1))
fi

if [ "$FINAL_XLEN" -lt "$FRAME_COUNT" ]; then
  echo "  D.14c PASS  XLEN=$FINAL_XLEN < total=$FRAME_COUNT (real loss observed)"
  PASS=$((PASS + 1))
else
  echo "  D.14c FAIL  XLEN=$FINAL_XLEN; kill landed too late (raise FRAME_COUNT or lower KILL_DELAY)"
  FAIL=$((FAIL + 1))
fi

echo
echo "=== summary: $PASS pass / $FAIL fail ==="
echo "log preserved at: $LOG"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
