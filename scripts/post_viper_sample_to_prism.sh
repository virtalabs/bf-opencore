#!/usr/bin/env bash
# POST an emitted Viper sample to a running Prism mock; exit 1 on non-2xx.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SAMPLE_PATH="${1:-/tmp/viper_sample.json}"
PRISM_BASE="${VIPER_PRISM_BASE_URL:-http://127.0.0.1:4010}"

if [[ ! -f "$SAMPLE_PATH" ]]; then
  echo "Sample not found: $SAMPLE_PATH" >&2
  exit 1
fi

CALLBACK=$(uv run python -c "
from blueflow.contracts.prism_viper import build_prism_callback_url
print(build_prism_callback_url('$PRISM_BASE'))
")

AUTH_HEADER=()
TOKEN="${VIPER_API_TOKEN:-contract-test-token}"
AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")

HTTP_CODE=$(curl -s -o /tmp/viper_prism_response.json -w "%{http_code}" \
  -X POST "$CALLBACK" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "@${SAMPLE_PATH}")

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "Prism rejected sample (HTTP $HTTP_CODE)" >&2
  cat /tmp/viper_prism_response.json >&2 || true
  exit 1
fi

echo "Prism accepted sample (HTTP $HTTP_CODE)"
