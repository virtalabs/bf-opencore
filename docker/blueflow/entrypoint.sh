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

exec python3 /app/stub_server.py 9000
