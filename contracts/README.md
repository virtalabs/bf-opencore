# BlueFlow contract fixtures (spike #188)

Consumer-side contract verification for BlueFlow's integration boundaries.
See `.cursor/context/TDD_Contract_Verification.md` for design and evolution path.

## Boundaries

| Boundary | Direction | CI tier | Mechanism |
|----------|-----------|---------|-----------|
| **A. BlueFlow → Viper** | Emitted webhook payload vs. Viper `integrationUpload` schema | Scheduled drift (`contracts.yml`, warn-only) | Live fetch of Viper `openapi.json`; `oasdiff` breaking classification vs. prior-run artifact baseline; payload validation |
| **B. TapirXL → BlueFlow** | Post-VRL upsert payloads | PR-blocking (`contracts.yml`) | Replay `contracts/tapirxl/golden_outputs.jsonl` through `PUT /api/assets/upsert/` |

Contract tests carry `@pytest.mark.contract` and are excluded from the Test workflow (`-m "not contract"`); they gate exclusively in Contracts CI.

No Viper spec is vendored in this repo. The live spec is fetched at drift-check time.

## `tapirxl/golden_outputs.jsonl`

Post-VRL payloads BlueFlow expects to ingest via upsert. **Provisional:** generated from
`blueflow/tests/fixtures/tapirxl_telemetry.jsonl` via the Python `_vrl_transform` mirror
in `blueflow/tests/test_tapirxl_viper_regression.py`. Replace with TapirXL-published
golden outputs when available.

### Refresh procedure

1. Update `blueflow/tests/fixtures/tapirxl_telemetry.jsonl` when TapirXL's golden set changes.
2. Regenerate outputs (same transform as the regression test mirror).
3. Update `contracts/tapirxl/manifest.yaml` (`fetched_at`, `sha256`, `upstream_ref`).
4. Open a PR; Contracts CI verify step must pass.

## Environment (drift steps only)

| Variable / secret | Purpose |
|-------------------|---------|
| `vars.VIPER_OPENAPI_URL` | URL to Viper's published `openapi.json` |
| `secrets.VIPER_API_TOKEN` | Bearer token for authenticated fetch (if required) |

Fetch or auth failure in the drift steps is a **warning**, never a PR block.

## Viper OpenAPI baseline artifact (drift)

Drift runs compare the **live** Viper `openapi.json` against the **previous successful drift run**, not a vendored file in this repo.

| Run | Baseline present? | Behavior |
|-----|-------------------|----------|
| First drift run | No | Skip `oasdiff`; notice "seeding baseline"; upload live spec |
| Subsequent runs | Yes | `oasdiff breaking` baseline vs live; warn on breaking changes; upload live spec |
| After 90-day retention expires | No | Same as first run (re-seed) |

**Artifact:** `viper-openapi-baseline` (`openapi.json` inside), uploaded at the end of each successful drift run. The next run downloads it via `dawidd6/action-download-artifact` (cross-run; standard `actions/download-artifact` only sees the current workflow run).

**Classification:** [`blueflow/contracts/diff_viper_openapi.py`](../blueflow/contracts/diff_viper_openapi.py) invokes [oasdiff](https://github.com/oasdiff/oasdiff) with `operationId:integrationUpload` filter. BlueFlow is a **consumer** of Viper's request schema, so baseline → live direction flags changes that break existing clients. Breaking changes emit `::warning::`; non-breaking changes emit `::notice::` with changelog output. The step uses `continue-on-error: true` — drift never blocks PRs.

**Local:** install `oasdiff` on PATH, then:

```bash
uv run python -m blueflow.contracts.diff_viper_openapi \
  --baseline /path/to/baseline/openapi.json \
  --live /path/to/live/openapi.json \
  --operation integrationUpload
```

