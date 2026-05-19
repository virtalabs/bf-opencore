# docker/

Container assets for BlueFlow.

## Layout

```text
docker/
  zeek/                # Standalone Zeek probe image (virtalabsinc/zeek-probe)
  zeek-test/           # E2E compose harness (BlueFlow + probe + traffic generator)
  _hl7-harness/        # Archived HL7 integration test harness (preserved, not maintained)
```

## `zeek/` — operational Zeek probe

The image deployed alongside BlueFlow to capture conn + ARP traffic on
a live interface and ship device observations to the API. Bundles
`blueflow/zeek/scripts/arp_extract.zeek` and `blueflow/zeek/sidecar.py`
at build time so a single `docker pull` gives the full ingest path.

See [`zeek/README.md`](zeek/README.md) for build, run, and DockerHub
push instructions.

## `_hl7-harness/` — archived

The end-to-end test rig that drove the HL7-only ingest pipeline (spike
#111). Preserved for reference; not wired into the current pipeline.
See [`_hl7-harness/README.md`](_hl7-harness/README.md) for the original
purpose and known-staleness caveats.
