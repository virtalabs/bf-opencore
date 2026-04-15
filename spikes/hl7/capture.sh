#!/usr/bin/env bash
# Usage: bash capture.sh <pcap_file> <output_dir>
#
# Runs tcpflow against a pcap file and writes reassembled TCP streams
# to the output directory. Each stream becomes a file named by its
# connection tuple (e.g., 192.168.056.001.42042-192.168.056.001.59185).

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: bash capture.sh <pcap_file> <output_dir>"
    exit 1
fi

PCAP="$1"
OUTDIR="$2"

if [ ! -f "$PCAP" ]; then
    echo "Error: pcap file not found: $PCAP"
    exit 1
fi

mkdir -p "$OUTDIR"

# L4/L7: reassemble TCP streams
tcpflow -r "$PCAP" -o "$OUTDIR"

# L2/L3: build MAC-IP mapping table
tshark -r "$PCAP" -T fields -e eth.src -e ip.src -Y "ip.src" 2>/dev/null \
    | sort -u > "$OUTDIR/mac_map.tsv"

STREAM_COUNT=$(find "$OUTDIR" -type f ! -name 'report.*' ! -name 'mac_map.tsv' | wc -l | tr -d ' ')
MAC_COUNT=$(wc -l < "$OUTDIR/mac_map.tsv" | tr -d ' ')
echo "Wrote $STREAM_COUNT stream(s) and $MAC_COUNT MAC mapping(s) to $OUTDIR"
