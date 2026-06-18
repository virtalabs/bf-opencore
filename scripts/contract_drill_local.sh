#!/usr/bin/env bash
# Local contract drill runner — proves gates can fail for the right reason.
# Prerequisites: uv sync --all-extras; optional oasdiff on PATH; Docker for Prism.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VIPER_FIXTURES="$ROOT/contracts/fixtures/viper"
PINNED_SPEC="$ROOT/contracts/viper/openapi.json"
SLICED_SPEC="/tmp/viper-sliced.json"
PRISM_CONTAINER=viper-prism-drill
FAILED=0
STARTED_PRISM=false

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }
skip() { echo "SKIP: $1"; }

stop_prism() {
  if [[ "$STARTED_PRISM" == true ]]; then
    docker rm -f "$PRISM_CONTAINER" >/dev/null 2>&1 || true
    STARTED_PRISM=false
  fi
}

start_prism() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  if [[ ! -f "$PINNED_SPEC" ]]; then
    echo "Missing pinned spec: $PINNED_SPEC" >&2
    return 1
  fi
  ./scripts/slice_viper_openapi.sh "$PINNED_SPEC" "$SLICED_SPEC"
  docker rm -f "$PRISM_CONTAINER" >/dev/null 2>&1 || true
  docker run --rm -d --name "$PRISM_CONTAINER" -p 4010:4010 \
    -v "$SLICED_SPEC:/spec/openapi.json:ro" \
    stoplight/prism:4 mock -h 0.0.0.0 /spec/openapi.json
  if ./scripts/wait_for_prism.sh http://127.0.0.1:4010/ "$PRISM_CONTAINER" 60; then
    export VIPER_PRISM_BASE_URL=http://127.0.0.1:4010
    export VIPER_API_TOKEN="${VIPER_API_TOKEN:-contract-test-token}"
    STARTED_PRISM=true
    return 0
  fi
  return 1
}

trap stop_prism EXIT

echo "=== 1. Contract tests (Prism wire when available) ==="
if start_prism; then
  if uv run pytest \
    blueflow/tests/test_contract_tapirxl_ingest.py \
    blueflow/tests/test_contract_viper_wire.py \
    blueflow/tests/test_diff_viper_openapi.py \
    -m "contract and not integration" -q; then
    pass "contract pytest suite"
  else
    fail "contract pytest suite"
  fi
else
  skip "docker unavailable — running tests without Prism wire suite"
  if uv run pytest \
    blueflow/tests/test_contract_tapirxl_ingest.py \
    blueflow/tests/test_diff_viper_openapi.py \
    -m "contract and not integration" -q; then
    pass "contract pytest (no wire)"
  else
    fail "contract pytest (no wire)"
  fi
fi

echo ""
echo "=== 2. oasdiff breaking change (fixture) ==="
if command -v oasdiff >/dev/null 2>&1; then
  if uv run python -m blueflow.contracts.diff_viper_openapi \
    --baseline "$VIPER_FIXTURES/baseline_openapi.json" \
    --live "$VIPER_FIXTURES/live_breaking_openapi.json" \
    --operation integrationUpload; then
    fail "oasdiff should report breaking changes (exit 1)"
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      fail "oasdiff failed to run (exit 2)"
    else
      pass "oasdiff detected breaking fixture drift"
    fi
  fi
else
  skip "oasdiff not on PATH"
fi

echo ""
echo "=== 3. Prism rejects invalid sample (fixture) ==="
if [[ "$STARTED_PRISM" == true ]]; then
  BAD_SAMPLE="$VIPER_FIXTURES/sample_page_missing_field.json"
  CALLBACK=$(uv run python -c "
from blueflow.contracts.prism_viper import build_prism_callback_url
print(build_prism_callback_url('$VIPER_PRISM_BASE_URL'))
")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$CALLBACK" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${VIPER_API_TOKEN}" \
    -d "$(python3 -c "import json; p=json.load(open('$BAD_SAMPLE')); p['next']=None; p['previous']=None; print(json.dumps(p))")")
  if [[ "$HTTP_CODE" -ge 400 ]]; then
    pass "Prism rejected non-conformant sample"
  else
    fail "Prism should reject bad sample (got HTTP $HTTP_CODE)"
  fi
else
  skip "Prism not running"
fi

echo ""
echo "=== 4. emit_viper_sample via Prism (optional, needs DB) ==="
if [[ -z "${DATABASE_URL:-}" ]]; then
  skip "DATABASE_URL not set"
elif [[ "$STARTED_PRISM" != true ]]; then
  skip "Prism not running"
else
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-project.settings.test}"
  uv run python project/manage.py migrate --noinput >/dev/null
  SAMPLE="/tmp/viper_drill_sample.json"
  if uv run python project/manage.py emit_viper_sample --output "$SAMPLE" \
    && ./scripts/post_viper_sample_to_prism.sh "$SAMPLE"; then
    pass "emit_viper_sample accepted by Prism"
  else
    fail "emit_viper_sample vs Prism"
  fi
fi

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "All required contract drills passed."
  exit 0
fi
echo "One or more contract drills failed."
exit 1
