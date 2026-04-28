# blueflow.zeek

Zeek log ingest for BlueFlow Asset records. Promoted from spike #111
(frozen at tag `zeek-hl7-spike-frozen`).

## Components

```
blueflow/zeek/
  __init__.py
  sidecar.py                 # Log loader + correlator + aggregator
  scripts/
    mllp.spicy               # Spicy grammar for MLLP framing
    mllp.evt                 # Event mapping (Spicy -> Zeek)
    hl7_extract.zeek         # HL7 field parsing into hl7.log
```

The Django management command `zeek_ingest`
(`blueflow/management/commands/zeek_ingest.py`) is the entry point:

```bash
python manage.py zeek_ingest --logdir /path/to/zeek/logs/
```

It expects `hl7.log` and (optionally) `conn.log` in JSON-mode Zeek output.
Assets are upserted by `mac_address`, with `open_ports_tcp` merged across
runs — same merge semantics as `PUT /api/assets/upsert/`.

## Field mapping

See the comment on issue #60 for the full mapping table. Currently
consumed: `name`, `serial_number`, `ip_address`, `mac_address`,
`open_ports_tcp`, plus HL7 context fields stored in `external_keys`.

## Running Zeek

The integration-test harness lives at `docker/` (compose + per-container
Dockerfiles + a non-docker local-run script). See `docker/README.md` for
details. Quick paths:

```bash
# 3-container end-to-end (host needs docker)
docker compose -f docker/docker-compose.yml up --build --abort-on-container-exit

# Local non-docker (host needs zeek + spicyz)
./docker/run-local.sh
```

Either path produces `hl7.log` + `conn.log` (compose: in
`/tmp/zeek-spike-logs/zeek/`; local: in `/tmp/zeek-test/`). Feed them to
the management command:

```bash
python manage.py zeek_ingest --logdir /tmp/zeek-test/
```
