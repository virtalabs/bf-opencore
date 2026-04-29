#!/usr/bin/env bash
set -euo pipefail
exec > >(tee /logs/output.log) 2>&1

echo "================================================"
echo "  Zeek Probe Container"
echo "================================================"
echo ""

# ── Step 1: Compile Spicy analyzer ──────────────────
echo "[1/5] Compiling MLLP Spicy analyzer..."
spicyz -o /work/mllp.hlto /scripts/mllp.spicy /scripts/mllp.evt
echo "      Done."
echo ""

# ── Step 2: Create veth pair for traffic capture ────
# tcpreplay sends on veth-replay, Zeek captures on veth-probe.
# Packets sent on one end of a veth pair arrive as incoming on the other.
echo "[2/5] Creating veth pair (veth-probe <-> veth-replay)..."
ip link add veth-probe type veth peer name veth-replay
ip link set veth-probe up
ip link set veth-replay up
echo "      Done."
echo ""

# ── Step 3: Start live capture on veth-probe ────────
echo "[3/5] Starting Zeek capture on veth-probe..."
cd /work
zeek -i veth-probe -C \
    /work/mllp.hlto \
    /scripts/hl7_extract.zeek \
    LogAscii::use_json=T &
ZEEK_PID=$!

# Don't signal ready until Zeek is still alive after startup. If it crashed
# (bad script, missing analyzer, no capture permission), fail fast instead of
# letting the traffic container replay into a dead probe.
for _ in $(seq 1 10); do
    if ! kill -0 "$ZEEK_PID" 2>/dev/null; then
        echo "      FAIL: Zeek exited before capture was ready" >&2
        wait "$ZEEK_PID" || exit $?
        exit 1
    fi
    sleep 0.5
done
touch /shared/zeek-ready
echo "      Zeek PID: $ZEEK_PID"
echo "      Signaled ready — waiting for traffic..."
echo ""

# ── Step 4: Wait for traffic, then stop Zeek ───────
echo "[4/5] Waiting for traffic replay..."
while [ ! -f /shared/traffic-done ]; do sleep 0.5; done
# Let Zeek finish processing the final packets
sleep 3

echo "      Traffic done. Stopping Zeek..."
kill "$ZEEK_PID" 2>/dev/null || true
zeek_status=0
wait "$ZEEK_PID" || zeek_status=$?
# 0 = clean exit, 143 = SIGTERM (the kill above). Anything else is a real failure.
if [ "$zeek_status" -ne 0 ] && [ "$zeek_status" -ne 143 ]; then
    echo "      FAIL: Zeek exited with status $zeek_status" >&2
    exit "$zeek_status"
fi
echo ""

echo "      Zeek log summary:"
for f in /work/*.log; do
    if [ -f "$f" ]; then
        lines=$(wc -l < "$f" | tr -d ' ')
        echo "        $(basename "$f"): $lines lines"
    fi
done

# Copy Zeek log files to /logs so they appear on the host
cp /work/*.log /logs/ 2>/dev/null || echo "      (no log files produced)"
echo ""

# ── Step 5: Run sidecar ────────────────────────────
# Wait for an upstream blueflow (stub or real) to signal ready, then read
# the URL + token it published. Falls back to the BLUEFLOW_URL env var if
# no sentinel was written (back-compat).
echo "[5/5] Waiting for blueflow ready..."
WAIT=0
while [ ! -f /shared/blueflow-ready ] && [ "$WAIT" -lt 120 ]; do
    sleep 1
    WAIT=$((WAIT + 1))
done
if [ ! -f /shared/blueflow-ready ]; then
    echo "      WARN: /shared/blueflow-ready never appeared; using \$BLUEFLOW_URL=$BLUEFLOW_URL"
fi
if [ -f /shared/api-url ]; then
    BLUEFLOW_URL="$(cat /shared/api-url)"
fi
TOKEN_ARG=""
if [ -f /shared/api-token ] && [ -s /shared/api-token ]; then
    TOKEN_ARG="--token $(cat /shared/api-token)"
    echo "      Using API token from /shared/api-token"
fi
echo "      Pushing to: $BLUEFLOW_URL"
echo "------------------------------------------------"
# shellcheck disable=SC2086 # TOKEN_ARG is intentionally unquoted to expand
python3 /app/sidecar.py /work/ --url "$BLUEFLOW_URL" $TOKEN_ARG
echo ""

echo "================================================"
echo "  Zeek pipeline complete"
echo "================================================"

# Signal traffic container that it can exit now
touch /shared/zeek-done
