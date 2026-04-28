# docker/ — integration test harness for the Zeek HL7 ingest pipeline

End-to-end test rig for `blueflow.zeek`. Three containers replay a pcap of
HL7 traffic into a live Zeek instance and verify the sidecar's HTTP push
to a stub BlueFlow endpoint.

This harness is preserved as the integration-test method for the Zeek
ingest path until/unless it is extracted into its own repo. Day-to-day
unit testing of the Python ingest path lives in
`blueflow/tests/test_zeek_ingest.py`.

## Layout

```
docker/
  docker-compose.yml          # 3-container compose
  run-local.sh                # non-docker local test (just zeek + sidecar)
  blueflow/
    Dockerfile                # python:3.12-slim — stub HTTP server only
    entrypoint.sh
    stub_server.py            # NOT real BlueFlow — accepts any PUT, returns 200
  zeek/
    Dockerfile                # zeek/zeek:latest + python3 + iproute2
    entrypoint.sh             # spicyz compile -> live capture -> sidecar push
  traffic/
    Dockerfile                # ubuntu + tcpreplay
    entrypoint.sh             # raw-IP -> ethernet rewrite -> tcpreplay
    raw2enet.py               # pcap link-type rewriter (DLT_RAW -> DLT_EN10MB)
```

The `blueflow` container here is a **stub** — it exists only so the
sidecar has somewhere to PUT. The repo-root `Dockerfile` is the real
BlueFlow image. Names match the spike's testing-method vocabulary;
renaming would change the mental model of the harness.

## Run

```bash
# 3-container end-to-end (compose)
docker compose -f docker/docker-compose.yml up --build --abort-on-container-exit

# Local non-docker (zeek + spicyz must be installed on host)
./docker/run-local.sh                              # defaults to spikes/hl7/data/hl7.pcap
./docker/run-local.sh path/to/capture.pcap         # custom pcap
SIDECAR=1 ./docker/run-local.sh                    # also run sidecar dry-run
```

Compose output lands at `/tmp/zeek-spike-logs/{blueflow,zeek,traffic}/`.
Local-run output lands at `/tmp/zeek-test/`.

## Verifying a compose run

After `docker compose ... up --abort-on-container-exit` exits, run the
verifier to assert hl7.log row count, upsert ledger count, unique-MAC
count, and per-payload structural invariants:

```bash
python3 docker/verify.py /tmp/zeek-spike-logs/                 # defaults
python3 docker/verify.py /tmp/zeek-spike-logs/ \
    --expect-hl7 124 --expect-upserts 1 --expect-macs 1
```

The stub server writes one JSONL row per request to
`/tmp/zeek-spike-logs/blueflow/upserts.jsonl` (override path with
`STUB_LEDGER_PATH`). The local-run path (`run-local.sh`) does its own
row-count assertion via `--expect <N>`.

## Build context note

The `zeek` service uses `context: ..` (repo root) so its Dockerfile can
`COPY blueflow/zeek/scripts/` and `blueflow/zeek/sidecar.py` from the
promoted Python package. The `blueflow` and `traffic` services use
per-folder context — everything they need is local.

## Pcap fixture

The HL7 sample pcap lives at `spikes/hl7/data/hl7.pcap` (124 messages,
1 device). It is mounted read-only into the `zeek` and `traffic`
containers via `../spikes/hl7/data:/pcap:ro`.

**Pcap files are not tracked by git** — `.gitignore` excludes `*.pcap`,
`*.pcapng`, `*.cap` and their gzipped variants because pcaps may carry
PHI. To populate the fixture for a fresh clone, see
`spikes/hl7/README.md`. The harness will fail with a clear error if
the pcap is missing.
