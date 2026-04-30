#!/usr/bin/env bash
# Run the Zeek MLLP/HL7 analyzer against a pcap file (no docker required).
#
# Usage (from repo root):
#   ./docker/run-local.sh                              # defaults: bundled pcap, expect 124
#   ./docker/run-local.sh path/to/capture.pcap
#   ./docker/run-local.sh --expect 530 path/to/other.pcap
#
# Exit codes:
#   0  — hl7.log row count == --expect (or default 124)
#   1  — pcap missing, tooling missing, or row-count mismatch
#
# Set SIDECAR=1 to additionally run the Python sidecar in dry-run mode
# (prints upsert payloads to stdout):
#   SIDECAR=1 ./docker/run-local.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ZEEK_PKG="$REPO_ROOT/blueflow/zeek"

OUTDIR="/tmp/zeek-test"
EXPECTED=124
PCAP=""

while [ $# -gt 0 ]; do
    case "$1" in
        --expect)
            EXPECTED="$2"
            shift 2
            ;;
        --expect=*)
            EXPECTED="${1#--expect=}"
            shift
            ;;
        -h|--help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *)
            PCAP="$1"
            shift
            ;;
    esac
done

PCAP="${PCAP:-$REPO_ROOT/blueflow/zeek/data/hl7.pcap}"

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

echo "Running Zeek against: $PCAP (expecting $EXPECTED HL7 messages)"
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
    command -v uv >/dev/null 2>&1 || { echo "Error: uv not found (required for SIDECAR=1)" >&2; exit 1; }
    echo ""
    echo "Running sidecar (dry-run)..."
    uv run "$ZEEK_PKG/sidecar.py" "$OUTDIR"
fi

if [ "$MSG_COUNT" -ne "$EXPECTED" ]; then
    echo "" >&2
    echo "FAIL: expected $EXPECTED HL7 messages, got $MSG_COUNT" >&2
    exit 1
fi

echo ""
echo "PASS: $MSG_COUNT == $EXPECTED expected"
