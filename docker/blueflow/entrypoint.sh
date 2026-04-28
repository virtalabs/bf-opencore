#!/usr/bin/env bash
set -euo pipefail
exec > >(tee /logs/output.log) 2>&1

echo "================================================"
echo "  BlueFlow Stub Server"
echo "================================================"
echo "Listening on :9000"
echo "All incoming requests will be logged below."
echo "------------------------------------------------"
echo ""

# Sentinel for the zeek container to know an upstream is reachable.
# Race window between touch and bind is microseconds for HTTPServer; fine
# for harness use.
mkdir -p /shared
printf '%s' "http://blueflow:9000" > /shared/api-url
touch /shared/blueflow-ready

exec python3 /app/stub_server.py 9000
