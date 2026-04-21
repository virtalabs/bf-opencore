# Spike #111 — Evaluate Zeek as On-Prem Probe for HL7 Passive Capture

Builds on the completed HL7 spike (#47). Evaluates whether Zeek can replace
tcpflow/tshark as the passive capture layer for MLLP-framed HL7 traffic.

## Structure

```
spikes/zeek/
  run.sh                               # Test runner (compile + run, output to /tmp)
  sidecar.py                           # Log-to-upsert sidecar prototype
  stub_server.py                       # Stub HTTP server for end-to-end testing
  data/                                # Sample pcap (reuses spikes/hl7/data/hl7.pcap)
  scripts/
    mllp.spicy                         # Spicy grammar for MLLP framing
    mllp.evt                           # Event mapping (Spicy -> Zeek)
    hl7_extract.zeek                   # HL7 field parsing and logging
  docs/
    research-notes.md                  # Phase 1 findings
    integration-architecture.md        # Integration design sketch
    111-zeek-evaluation.md             # Final decision note
```

## Prerequisites

- Zeek + Spicy (`brew install zeek` on macOS, `apt install zeek` on Debian/Ubuntu)
- Sample pcap at `spikes/hl7/data/hl7.pcap` (124 HL7 messages, 1 device)

## Quick start

```bash
# Run the full pipeline (compile Spicy analyzer, run Zeek, report)
./spikes/zeek/run.sh

# With a custom pcap
./spikes/zeek/run.sh path/to/capture.pcap

# Output lands in /tmp/zeek-test/ (JSON format)
cat /tmp/zeek-test/hl7.log    # Extracted HL7 messages
cat /tmp/zeek-test/conn.log   # Connection metadata
```

## Sidecar prototype

The sidecar reads Zeek JSON logs, correlates across log types, and produces
upsert payloads compatible with `PUT /api/assets/upsert/`.

```bash
# Dry-run: print upsert payloads to stdout
uv run spikes/zeek/sidecar.py /tmp/zeek-test/

# Run Zeek + sidecar together
SIDECAR=1 ./spikes/zeek/run.sh

# End-to-end with stub server (no BlueFlow needed)
uv run spikes/zeek/stub_server.py &                           # terminal 1
uv run spikes/zeek/sidecar.py /tmp/zeek-test/ --url http://localhost:8000  # terminal 2

# Against a real BlueFlow instance
uv run spikes/zeek/sidecar.py /tmp/zeek-test/ --url http://localhost:8000 --token <tok>
```

### Synthetic MAC addresses

When Zeek replays pcap files (rather than live capture), Layer 2 MAC addresses
are unavailable from `conn.log`. The sidecar generates a deterministic
locally-administered MAC from the device IP: `02:00:xx:xx:xx:xx`. The `02:00`
prefix avoids collision with real OUI-assigned MACs. Re-runs against the same
pcap produce the same MAC, so upserts are idempotent.

## Notes

- The `-C` flag is used to ignore checksum errors (common in loopback/test pcaps)
- The sample pcap uses port 42042 (non-standard); the analyzer also registers port 2575 (IANA MLLP)
- Spicy analyzers must be precompiled with `spicyz` — `run.sh` handles this automatically
- Zeek outputs JSON format (`LogAscii::use_json=T`) for sidecar consumption

## Phases

1. **Research** (complete) — No existing HL7/MLLP analyzer; Spicy grammar recommended;
   Zeek fits small hospital deployment (1 core, 1-2 GB RAM)
2. **Prototype** (complete) — Spicy MLLP analyzer produces 124/124 message parity with
   the #47 tcpflow/tshark pipeline
3. **Decision** (complete) — Adopt Zeek as probe platform with HTTP-push integration;
   supports remote, multi-probe deployments

## Related issues

- #47 — HL7 passive capture spike (complete)
- #48 — FHIR spike
- #49 — Naabu + Zeek integration (depends on this spike)
- #44 — DICOM/AE Title spike
