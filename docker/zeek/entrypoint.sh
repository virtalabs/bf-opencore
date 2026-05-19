#!/usr/bin/env bash
#
# Long-running entrypoint for the standalone Zeek probe.
#
# Lifecycle:
#   1. Validate required env (ZEEK_INTERFACE, BLUEFLOW_URL).
#   2. Start Zeek in the background on $ZEEK_INTERFACE with JSON logs +
#      the bundled arp_extract.zeek log policy.
#   3. Loop: every PUSH_INTERVAL_SECONDS, invoke the sidecar to PUT every
#      device it can extract from the current conn.log + arp.log to the
#      configured BlueFlow. Asset upsert is idempotent on mac_address, so
#      pushing cumulative logs each cycle is safe (open_ports_tcp merges).
#   4. On SIGTERM / SIGINT, stop Zeek cleanly, do a final push, exit 0.
#
# Logs grow unbounded inside the container for the MVP. Restart the
# container or wire in `Log::default_rotation_interval` if that becomes a
# problem.

set -euo pipefail

# ── Required env ────────────────────────────────────────────────
: "${ZEEK_INTERFACE:?ZEEK_INTERFACE must be set (e.g. eth0)}"
: "${BLUEFLOW_URL:?BLUEFLOW_URL must be set (e.g. http://blueflow.internal:8000)}"

# ── Optional env ────────────────────────────────────────────────
PUSH_INTERVAL_SECONDS="${PUSH_INTERVAL_SECONDS:-60}"
BLUEFLOW_TOKEN="${BLUEFLOW_TOKEN:-}"
ZEEK_LOG_DIR="${ZEEK_LOG_DIR:-/var/log/zeek}"

# Guard the push loop: a non-numeric or zero interval would either
# fail the `sleep` immediately or busy-loop the API with pushes.
if ! [[ "$PUSH_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [ "$PUSH_INTERVAL_SECONDS" -lt 1 ]; then
    echo "[zeek-probe] FAIL: PUSH_INTERVAL_SECONDS must be a positive integer (got '$PUSH_INTERVAL_SECONDS')" >&2
    exit 1
fi

echo "[zeek-probe] interface=$ZEEK_INTERFACE upstream=$BLUEFLOW_URL push_interval=${PUSH_INTERVAL_SECONDS}s log_dir=$ZEEK_LOG_DIR"

mkdir -p "$ZEEK_LOG_DIR"
cd "$ZEEK_LOG_DIR"

# ── Start Zeek in the background ────────────────────────────────
# JSON output is required by the sidecar's load_log() parser.
zeek -i "$ZEEK_INTERFACE" \
     /opt/blueflow-zeek/scripts/arp_extract.zeek \
     LogAscii::use_json=T &
ZEEK_PID=$!
echo "[zeek-probe] zeek pid=$ZEEK_PID"

# Fail-fast if Zeek crashed on startup (bad interface name, missing
# capability, parse error). 5s window mirrors the HL7 harness probe.
for _ in $(seq 1 10); do
    if ! kill -0 "$ZEEK_PID" 2>/dev/null; then
        echo "[zeek-probe] FAIL: zeek exited before capture was ready" >&2
        wait "$ZEEK_PID" || exit $?
        exit 1
    fi
    sleep 0.5
done
echo "[zeek-probe] zeek alive after 5s — capture started"

# ── Push helper ─────────────────────────────────────────────────
push_logs() {
    local token_arg=""
    [ -n "$BLUEFLOW_TOKEN" ] && token_arg="--token $BLUEFLOW_TOKEN"
    # shellcheck disable=SC2086  # token_arg expands to two args or none
    python3 /opt/blueflow-zeek/sidecar.py "$ZEEK_LOG_DIR" \
        --url "$BLUEFLOW_URL" $token_arg
}

# ── Signal handling: clean stop + final push ────────────────────
shutting_down=0
cleanup() {
    [ "$shutting_down" -eq 1 ] && return
    shutting_down=1
    echo "[zeek-probe] signal received, stopping zeek..."
    kill "$ZEEK_PID" 2>/dev/null || true
    wait "$ZEEK_PID" 2>/dev/null || true
    echo "[zeek-probe] final push..."
    push_logs || echo "[zeek-probe] WARN: final push failed"
    echo "[zeek-probe] exiting cleanly"
    exit 0
}
trap cleanup TERM INT

# ── Main push loop ──────────────────────────────────────────────
while kill -0 "$ZEEK_PID" 2>/dev/null; do
    sleep "$PUSH_INTERVAL_SECONDS" &
    SLEEP_PID=$!
    wait "$SLEEP_PID" || true     # interruptible by trap
    if ! kill -0 "$ZEEK_PID" 2>/dev/null; then break; fi
    echo "[zeek-probe] push cycle..."
    push_logs || echo "[zeek-probe] WARN: push failed; will retry next cycle"
done

echo "[zeek-probe] zeek exited unexpectedly; final push + bail"
push_logs || true
wait "$ZEEK_PID" 2>/dev/null
exit $?
