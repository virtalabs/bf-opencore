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

The compose-based test harness (`docker-compose.yml`, `Dockerfile.*`,
`run.sh`) was not promoted from the spike. To run it locally, check out
the frozen tag in a worktree:

```bash
git worktree add /tmp/zeek-spike zeek-hl7-spike-frozen
cd /tmp/zeek-spike/spikes/zeek
./run.sh
```

The frozen harness writes `hl7.log` + `conn.log` to `/tmp/zeek-test/`,
which can then be ingested via:

```bash
python manage.py zeek_ingest --logdir /tmp/zeek-test/
```
