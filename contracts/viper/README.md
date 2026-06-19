# Viper OpenAPI contract (BlueFlow consumer)

Committed snapshot of Viper's published OpenAPI spec. PR contract tests slice this
file at runtime and validate outbound integration upload payloads against a Prism mock.

## Pin

| File | Purpose |
|------|---------|
| `openapi.json` | Pinned upstream spec — the contract revision BlueFlow tests against |

Scheduled drift compares live spec to this file. When they differ, a bot opens a PR
to update the pin.

## Manual refresh

```bash
curl -sf https://viper-xi.vercel.app/api/openapi.json -o contracts/viper/openapi.json
```

Or set `VIPER_OPENAPI_URL` and optional `VIPER_API_TOKEN` for authenticated fetch.

## Local Prism + wire tests

Requires Docker.

```bash
./scripts/slice_viper_openapi.sh contracts/viper/openapi.json /tmp/viper-sliced.json

docker run --rm -d --name viper-prism -p 4010:4010 \
  -v "/tmp/viper-sliced.json:/spec/openapi.json:ro" \
  stoplight/prism:4 mock -h 0.0.0.0 /spec/openapi.json

export VIPER_PRISM_BASE_URL=http://127.0.0.1:4010
export VIPER_API_TOKEN=contract-test-token
export VIPER_CALLBACK_ALLOWED_HOSTS=127.0.0.1
export DATABASE_URL=postgresql://blueflow:blueflow@localhost:5432/blueflow
export DJANGO_SETTINGS_MODULE=project.settings.test

# Default pytest skips @pytest.mark.contract; -m contract is required.
uv run pytest blueflow/tests/test_contract_viper_wire.py -m contract -v

docker rm -f viper-prism
```

Or run `./scripts/contract_drill_local.sh` (slices pin, starts Prism when Docker is available).

## Environment variables

| Variable | Used by |
|----------|---------|
| `VIPER_OPENAPI_URL` | Drift job fetch (optional repo variable; defaults to viper-xi URL) |
| `VIPER_API_TOKEN` | Fetch auth (optional); Bearer header on outbound POSTs when callback host is allowlisted |
| `VIPER_CALLBACK_ALLOWED_HOSTS` | Comma-separated callback hosts permitted to receive Bearer auth (required with `VIPER_API_TOKEN`). Hostname only — `127.0.0.1` does not match `localhost`; use `127.0.0.1` in `VIPER_PRISM_BASE_URL` and allowlist consistently. |
| `VIPER_CALLBACK_TIMEOUT` | Outbound callback POST timeout in seconds (optional; default `30`) |
| `VIPER_PRISM_BASE_URL` | Wire tests (e.g. `http://127.0.0.1:4010`) |
| `VIPER_INTEGRATION_TOKEN` | Path param for callback URL (default: `contract-test-token`) |
