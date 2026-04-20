# Spike #111 — Evaluate Zeek as On-Prem Probe for HL7 Passive Capture

Builds on the completed HL7 spike (#47). Evaluates whether Zeek can replace
tcpflow/tshark as the passive capture layer for MLLP-framed HL7 traffic.

## Structure

```
spikes/zeek/
  run.sh                               # Test runner (compile + run, output to /tmp)
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

# Output lands in /tmp/zeek-test/
cat /tmp/zeek-test/hl7.log    # Extracted HL7 messages
cat /tmp/zeek-test/conn.log   # Connection metadata
```

## Notes

- The `-C` flag is used to ignore checksum errors (common in loopback/test pcaps)
- The sample pcap uses port 42042 (non-standard); the analyzer also registers port 2575 (IANA MLLP)
- Spicy analyzers must be precompiled with `spicyz` — `run.sh` handles this automatically

## Phases

1. **Research** (complete) — No existing HL7/MLLP analyzer; Spicy grammar recommended;
   Zeek fits small hospital deployment (1 core, 1-2 GB RAM)
2. **Prototype** (complete) — Spicy MLLP analyzer produces 124/124 message parity with
   the #47 tcpflow/tshark pipeline
3. **Decision** — Recommend adopt / partial / stay with tcpflow+tshark

## Related issues

- #47 — HL7 passive capture spike (complete)
- #48 — FHIR spike
- #49 — Naabu + Zeek integration (depends on this spike)
- #44 — DICOM/AE Title spike
