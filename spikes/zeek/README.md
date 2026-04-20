# Spike #111 — Evaluate Zeek as On-Prem Probe for HL7 Passive Capture

Builds on the completed HL7 spike (#47). Evaluates whether Zeek can replace
tcpflow/tshark as the passive capture layer for MLLP-framed HL7 traffic.

## Structure

```
spikes/zeek/
  data/                        # Sample pcap (reuses spikes/hl7/data/hl7.pcap)
  scripts/                     # Zeek scripts (Phase 2)
    hl7_extract.zeek           # MLLP/HL7 extraction script
  docs/
    research-notes.md          # Phase 1 findings
    integration-architecture.md  # Integration design sketch
    111-zeek-evaluation.md     # Final decision note
```

## Prerequisites

- Zeek (`brew install zeek` on macOS, `apt install zeek` on Debian/Ubuntu)
- Sample pcap at `spikes/hl7/data/hl7.pcap` (124 HL7 messages, 1 device)

## Quick start

```bash
# Verify Zeek processes the sample pcap
zeek -r spikes/hl7/data/hl7.pcap

# Run the HL7 extraction script (once written)
zeek -r spikes/hl7/data/hl7.pcap spikes/zeek/scripts/hl7_extract.zeek
```

## Phases

1. **Research** — Assess HL7/MLLP analyzers, map Zeek logs to BlueFlow Asset fields,
   evaluate deployment viability
2. **Prototype** — Write a Zeek script to extract HL7 data from the sample pcap
3. **Decision** — Recommend adopt / partial / stay with tcpflow+tshark

## Related issues

- #47 — HL7 passive capture spike (complete)
- #48 — FHIR spike
- #49 — Naabu + Zeek integration (depends on this spike)
- #44 — DICOM/AE Title spike
