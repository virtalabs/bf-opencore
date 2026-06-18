#!/usr/bin/env bash
# Slice Viper OpenAPI to one operation for Prism mock.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT="${1:-$ROOT/contracts/viper/openapi.json}"
OUTPUT="${2:-/tmp/viper-sliced.json}"
OPERATION="${3:-assets-processIntegrationCreate}"

if [[ ! -f "$INPUT" ]]; then
  echo "OpenAPI spec not found: $INPUT" >&2
  exit 1
fi

uv run python -c "
import json, sys
from pathlib import Path
from blueflow.contracts.diff_viper_openapi import slice_openapi_for_operation
inp, out, op = sys.argv[1], sys.argv[2], sys.argv[3]
spec = json.loads(Path(inp).read_text(encoding='utf-8'))
Path(out).write_text(json.dumps(slice_openapi_for_operation(spec, op), indent=2) + '\n')
" "$INPUT" "$OUTPUT" "$OPERATION"
