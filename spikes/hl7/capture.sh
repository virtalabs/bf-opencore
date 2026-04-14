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
tcpflow -r "$PCAP" -o "$OUTDIR"

STREAM_COUNT=$(find "$OUTDIR" -type f ! -name 'report.*' | wc -l | tr -d ' ')
echo "Wrote $STREAM_COUNT stream(s) to $OUTDIR"
