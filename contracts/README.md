# BlueFlow contract fixtures (spike #188)

Consumer-side contract verification for BlueFlow's integration boundaries.
See `.cursor/context/TDD_Contract_Verification.md` for design and evolution path.

## Boundaries

| Boundary | Direction | CI tier | Mechanism |
|----------|-----------|---------|-----------|
| **A. BlueFlow → Viper** | Emitted webhook payload vs. Viper `integrationUpload` schema | Scheduled drift (`contracts.yml` `drift` job) | Live fetch of Viper `openapi.json`; warn-only on failure |
| **B. TapirXL → BlueFlow** | Post-VRL upsert payloads | PR-blocking (`contracts.yml` `verify` job) | Replay `contracts/tapirxl/golden_outputs.jsonl` through `PUT /api/assets/upsert/` |

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
4. Open a PR; `contracts.yml` `verify` must pass.

## Environment (drift job only)

| Variable / secret | Purpose |
|-------------------|---------|
| `vars.VIPER_OPENAPI_URL` | URL to Viper's published `openapi.json` |
| `secrets.VIPER_API_TOKEN` | Bearer token for authenticated fetch (if required) |

Fetch or auth failure in the drift job is a **warning**, never a PR block.
