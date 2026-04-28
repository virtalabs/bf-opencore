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

# Give Zeek a moment to open the capture socket before signaling ready
sleep 2
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
wait "$ZEEK_PID" 2>/dev/null || true
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
echo "[5/5] Running sidecar -> $BLUEFLOW_URL"
echo "------------------------------------------------"
python3 /app/sidecar.py /work/ --url "$BLUEFLOW_URL"
echo ""

echo "================================================"
echo "  Zeek pipeline complete"
echo "================================================"

# Signal traffic container that it can exit now
touch /shared/zeek-done
