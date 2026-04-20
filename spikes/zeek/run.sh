#!/usr/bin/env bash
# Run the Zeek MLLP/HL7 analyzer against a pcap file.
#
# Usage:
#   ./run.sh                          # defaults to spikes/hl7/data/hl7.pcap
#   ./run.sh path/to/capture.pcap

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="/tmp/zeek-test"
PCAP="${1:-$(dirname "$SCRIPT_DIR")/hl7/data/hl7.pcap}"

if [ ! -f "$PCAP" ]; then
    echo "Error: pcap not found: $PCAP" >&2
    exit 1
fi

command -v zeek  >/dev/null 2>&1 || { echo "Error: zeek not found"  >&2; exit 1; }
command -v spicyz >/dev/null 2>&1 || { echo "Error: spicyz not found" >&2; exit 1; }

mkdir -p "$OUTDIR"

# Compile the Spicy MLLP analyzer
echo "Compiling MLLP analyzer..."
spicyz -o "$OUTDIR/mllp.hlto" \
    "$SCRIPT_DIR/scripts/mllp.spicy" \
    "$SCRIPT_DIR/scripts/mllp.evt"

# Run Zeek (-C ignores checksum errors common in loopback/test pcaps)
echo "Running Zeek against: $PCAP"
cd "$OUTDIR" && rm -f *.log
zeek -Cr "$PCAP" \
    "$OUTDIR/mllp.hlto" \
    "$SCRIPT_DIR/scripts/hl7_extract.zeek"

# Report
MSG_COUNT=$(grep -cv '^#' "$OUTDIR/hl7.log" 2>/dev/null || echo 0)
echo ""
echo "Done. $MSG_COUNT HL7 messages extracted."
echo "Logs: $OUTDIR/"
ls -1 "$OUTDIR"/*.log
