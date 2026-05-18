# blueflow.zeek.hl7

Archived HL7-specific Zeek ingest. Preserved from spike #111
(`zeek-hl7-spike-frozen` tag), originally promoted to `blueflow/zeek/`
in the HL7 phase. Moved here when the ingest pipeline pivoted to the
broader conn.log + arp.log path.

Nothing in this subpackage is wired into the live `zeek_ingest`
management command anymore; the new command drives
`blueflow.zeek.sidecar`. Tests under `tests/` still exercise this
module's correlation + aggregation logic so the archived path doesn't
silently rot.

## Files

```text
hl7/
  sidecar.py                 # hl7.log + conn.log -> AssetUpsertSerializer payloads
  scripts/
    mllp.spicy               # Spicy grammar for MLLP framing
    mllp.evt                 # Event mapping (Spicy -> Zeek)
    hl7_extract.zeek         # HL7 field parsing into hl7.log
  tests/
    test_zeek_ingest.py      # unit tests for sidecar correlation + aggregation
```

To run Zeek against an HL7 pcap and feed the result into this sidecar
manually:

```bash
zeek -Cr <pcap> blueflow/zeek/hl7/scripts/mllp.spicy \
                blueflow/zeek/hl7/scripts/mllp.evt \
                blueflow/zeek/hl7/scripts/hl7_extract.zeek
python -c "from pathlib import Path; from blueflow.zeek.hl7.sidecar import payloads_from_logdir; \
           import json; print(json.dumps(payloads_from_logdir(Path('.')), indent=2))"
```
