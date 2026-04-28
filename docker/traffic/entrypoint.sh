#!/usr/bin/env bash
set -euo pipefail
exec > >(tee /logs/output.log) 2>&1

echo "================================================"
echo "  Traffic Replay Container"
echo "================================================"
echo ""

PCAP="/pcap/hl7.pcap"
if [ ! -f "$PCAP" ]; then
    echo "ERROR: pcap not found at $PCAP"
    exit 1
fi

SIZE=$(du -h "$PCAP" | cut -f1)
echo "Pcap:    $PCAP ($SIZE)"

# The sample pcap uses Raw IP link type (no Ethernet headers) because it was
# captured on loopback. veth pairs are Ethernet interfaces, so we wrap each
# packet in an Ethernet frame before replay.
echo "Rewriting pcap: Raw IP -> Ethernet framing..."
ENET_PCAP="/tmp/hl7-enet.pcap"
python3 /app/raw2enet.py "$PCAP" "$ENET_PCAP"
echo ""

echo "Waiting for Zeek to be ready..."
while [ ! -f /shared/zeek-ready ]; do sleep 0.5; done

echo "Zeek is ready. Replaying..."
echo "------------------------------------------------"
echo ""

tcpreplay --intf1=veth-replay --pps=500 "$ENET_PCAP" 2>&1

echo ""
echo "------------------------------------------------"
echo "Replay complete."

touch /shared/traffic-done

echo "Waiting for Zeek to finish processing..."
while [ ! -f /shared/zeek-done ]; do sleep 1; done

echo "================================================"
echo "  Traffic replay done"
echo "================================================"
