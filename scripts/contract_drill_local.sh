#!/usr/bin/env bash
# Local contract drill runner — proves gates can fail for the right reason.
# Prerequisites: uv sync --all-extras; optional oasdiff on PATH; DATABASE_URL for section 4.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VIPER_FIXTURES="$ROOT/contracts/fixtures/viper"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }
skip() { echo "SKIP: $1"; }

echo "=== 1. Permanent negative contract tests ==="
if uv run pytest \
  blueflow/tests/test_contract_tapirxl_ingest.py \
  blueflow/tests/test_check_viper_payload.py \
  blueflow/tests/test_diff_viper_openapi.py \
  -m "contract and not integration" -q; then
  pass "permanent negative tests"
else
  fail "permanent negative tests"
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
echo "=== 3. Viper payload validation break (fixture) ==="
if uv run python -m blueflow.contracts.check_viper_payload \
  --spec "$VIPER_FIXTURES/live_breaking_openapi.json" \
  --sample "$VIPER_FIXTURES/sample_page.json"; then
  fail "check_viper_payload should fail against breaking spec"
else
  pass "payload validation rejected non-conformant sample"
fi

echo ""
echo "=== 4. Viper payload happy path (optional, needs DB) ==="
if [[ -z "${DATABASE_URL:-}" ]]; then
  skip "DATABASE_URL not set"
else
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-project.settings.test}"
  uv run python project/manage.py migrate --noinput >/dev/null
  SAMPLE="/tmp/viper_drill_sample.json"
  if uv run python project/manage.py emit_viper_sample --output "$SAMPLE" \
    && uv run python -m blueflow.contracts.check_viper_payload \
      --spec "$VIPER_FIXTURES/baseline_openapi.json" \
      --sample "$SAMPLE"; then
    pass "emit_viper_sample validates against baseline fixture"
  else
    fail "emit_viper_sample vs baseline fixture"
  fi
fi

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "All required contract drills passed."
  exit 0
fi
echo "One or more contract drills failed."
exit 1
