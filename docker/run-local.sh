#!/usr/bin/env bash
# Run the Zeek MLLP/HL7 analyzer against a pcap file (no docker required).
#
# Usage (from repo root):
#   ./docker/run-local.sh                          # defaults to spikes/hl7/data/hl7.pcap
#   ./docker/run-local.sh path/to/capture.pcap
#
# Set SIDECAR=1 to additionally run the Python sidecar in dry-run mode
# (prints upsert payloads to stdout):
#   SIDECAR=1 ./docker/run-local.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ZEEK_PKG="$REPO_ROOT/blueflow/zeek"

OUTDIR="/tmp/zeek-test"
PCAP="${1:-$REPO_ROOT/spikes/hl7/data/hl7.pcap}"

if [ ! -f "$PCAP" ]; then
    echo "Error: pcap not found: $PCAP" >&2
    exit 1
fi

command -v zeek   >/dev/null 2>&1 || { echo "Error: zeek not found"   >&2; exit 1; }
command -v spicyz >/dev/null 2>&1 || { echo "Error: spicyz not found" >&2; exit 1; }

mkdir -p "$OUTDIR"

echo "Compiling MLLP analyzer..."
spicyz -o "$OUTDIR/mllp.hlto" \
    "$ZEEK_PKG/scripts/mllp.spicy" \
    "$ZEEK_PKG/scripts/mllp.evt"

echo "Running Zeek against: $PCAP"
cd "$OUTDIR" && rm -f *.log
zeek -Cr "$PCAP" \
    "$OUTDIR/mllp.hlto" \
    "$ZEEK_PKG/scripts/hl7_extract.zeek" \
    LogAscii::use_json=T

MSG_COUNT=$(wc -l < "$OUTDIR/hl7.log" 2>/dev/null | tr -d ' ')
echo ""
echo "Done. $MSG_COUNT HL7 messages extracted."
echo "Logs: $OUTDIR/"
ls -1 "$OUTDIR"/*.log

if [ "${SIDECAR:-}" = "1" ]; then
    echo ""
    echo "Running sidecar (dry-run)..."
    uv run "$ZEEK_PKG/sidecar.py" "$OUTDIR"
fi
