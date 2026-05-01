# docker/ — integration test harness for the Zeek HL7 ingest pipeline

End-to-end test rig for `blueflow.zeek`. Containers replay a pcap of
HL7 traffic into a live Zeek instance and verify the sidecar's HTTP push
to a BlueFlow endpoint. Two compose profiles select what's on the
receiving end:

- **`stub`** — a tiny Python `HTTPServer` that accepts any PUT and writes
  a JSONL ledger. Fast (~3s start), no DB. Exercises plumbing only.
- **`real`** — the actual BlueFlow image + ephemeral Postgres. Exercises
  serializer validation, ORM upsert, entity resolution.

The harness is preserved as the integration-test method for the Zeek
ingest path until/unless it is extracted into its own repo. Day-to-day
unit testing of the Python ingest path lives in
`blueflow/tests/test_zeek_ingest.py`.

## Layout

```text
docker/
  docker-compose.yml          # 5-service compose (stub + real profiles)
  run-local.sh                # non-docker zeek + sidecar local run
  verify.py                   # post-run assertion script (stub mode)
  blueflow/                   # [stub profile]
    Dockerfile                # python:3.12-slim — stub HTTP server only
    entrypoint.sh
    stub_server.py            # NOT real BlueFlow — accepts any PUT, returns 200
  blueflow-real/              # [real profile]
    bootstrap.sh              # migrate + waffle + token, then exec runserver
                              # (mounted into the repo-root BlueFlow image)
  zeek/                       # always runs
    Dockerfile                # zeek/zeek:latest + python3 + iproute2
    entrypoint.sh             # spicyz compile -> live capture -> sidecar push
  traffic/                    # always runs
    Dockerfile                # ubuntu + tcpreplay
    entrypoint.sh             # raw-IP -> ethernet rewrite -> tcpreplay
    raw2enet.py               # pcap link-type rewriter (DLT_RAW -> DLT_EN10MB)
```

The `blueflow` (stub) container is a Python `HTTPServer`, not the real
BlueFlow image. The repo-root `Dockerfile` is what `blueflow-real`
builds from. Names match the spike's testing-method vocabulary.

## Run

```bash
# Stub profile — fast plumbing test, no DB
docker compose -f docker/docker-compose.yml --profile stub up --build --abort-on-container-exit

# Real profile — actual BlueFlow + ephemeral Postgres
docker compose -f docker/docker-compose.yml --profile real up --build --abort-on-container-exit

# Custom pcap directory + filename (works with either profile)
PCAP_DIR=/path/to/my/pcaps PCAP_FILE=multi-device.pcap \
    docker compose -f docker/docker-compose.yml --profile stub up --build --abort-on-container-exit

# Local non-docker (zeek + spicyz must be installed on host)
./docker/run-local.sh                              # defaults to blueflow/zeek/data/hl7.pcap
./docker/run-local.sh path/to/capture.pcap         # custom pcap
./docker/run-local.sh --expect 530 path/to/big.pcap
SIDECAR=1 ./docker/run-local.sh                    # also run sidecar dry-run
```

You **must** specify `--profile stub` or `--profile real`. A bare
`docker compose ... up` only starts `zeek` + `traffic`, both of which
block waiting for `/shared/blueflow-ready` from an upstream that isn't
running.

### How the upstream selection works

Both profiles write `/shared/api-url` (and the real profile also writes
`/shared/api-token`) before touching `/shared/blueflow-ready`. The zeek
container blocks on that sentinel and reads the URL/token from the
shared volume. So the same `zeek` service points at either upstream
without per-profile env wiring.

### Pcap selection

`PCAP_DIR` (host path, default `../blueflow/zeek/data`) is bind-mounted to
`/pcap` in the `zeek` and `traffic` containers. `PCAP_FILE` (default
`hl7.pcap`) is the filename inside that directory. Both have sensible
defaults so the bare `up` command works out of the box.

Compose output lands at `/tmp/zeek-spike-logs/{blueflow,blueflow-real,zeek,traffic}/`.
Local-run output lands at `/tmp/zeek-test/`.

## Verifying a stub run

After a `--profile stub` run, the stub server's JSONL ledger is on the
host:

```bash
python3 docker/verify.py /tmp/zeek-spike-logs/                 # defaults
python3 docker/verify.py /tmp/zeek-spike-logs/ \
    --expect-hl7 124 --expect-upserts 1 --expect-macs 1
```

The verifier asserts `hl7.log` row count, upsert ledger count, unique-MAC
count, and per-payload structural invariants. The local-run path
(`run-local.sh`) does its own row-count assertion via `--expect <N>`.

## Verifying a real run

The bootstrap script writes the API token to a `tmpfs` shared volume
(`/shared/api-token`) for the in-container sidecar handoff only — it
is **not** persisted to the host-visible logs volume. To query the
running API after a `--profile real` run, exec into the container or
mint a fresh token:

```bash
docker exec zeek-spike-blueflow-real cat /shared/api-token
# or, with the container still up:
TOKEN=$(docker exec zeek-spike-blueflow-real cat /shared/api-token)
curl -sH "Authorization: Token $TOKEN" http://localhost:8000/api/assets/ | jq '.count, .results[].mac_address'
```

A formal `verify-real.py` is on the test-tier roadmap (T4c) but not yet
shipped — for now this manual check is the post-condition.

## Build context note

The `zeek` service uses `context: ..` (repo root) so its Dockerfile can
`COPY blueflow/zeek/scripts/` and `blueflow/zeek/sidecar.py` from the
promoted Python package. `blueflow-real` also uses repo-root context to
build from the canonical `Dockerfile`. The `blueflow` (stub) and
`traffic` services use per-folder context — everything they need is
local.

## Pcap fixture

The HL7 sample pcap lives at `blueflow/zeek/data/hl7.pcap` (124 messages,
1 device). It is mounted read-only into the `zeek` and `traffic`
containers via `../blueflow/zeek/data:/pcap:ro`.

**Pcap files are not tracked by git** — `.gitignore` excludes `*.pcap`,
`*.pcapng`, `*.cap` and their gzipped variants because pcaps may carry
PHI. The `blueflow/zeek/data/.gitignore` additionally walls off the
directory's contents so only the `.gitignore` itself is tracked. To
populate the fixture for a fresh clone, see `blueflow/zeek/README.md`.
The harness will fail with a clear error if the pcap is missing.
