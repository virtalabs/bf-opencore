# HL7 Passive Capture Spike

Prototype pipeline for discovering medical devices from HL7 v2.x traffic captured off a SPAN port or tap.

**Issue:** #47
**Spike doc:** [docs/047-hl7-passive-scanning.md](docs/047-hl7-passive-scanning.md)

## Prerequisites

```bash
brew install tcpflow wireshark   # tcpflow + tshark
uv sync --all-extras             # python-hl7
```

## Pipeline

```bash
./extract.py <pcap_file> | ./emit.py
```

Two scripts, one pipe, no intermediate files.

| Script | Job | Input | Output |
|---|---|---|---|
| `extract.py` | Capture + parse + enrich | pcap file | JSON lines (stdout) |
| `emit.py` | Conform to Asset model | JSON lines (stdin) | Asset records (stdout) |

`extract.py` runs tcpflow (TCP stream reassembly) and tshark (MAC-IP mapping) internally, parses MLLP-framed HL7 messages, correlates MAC addresses, and emits one JSON line per message. ACK messages are filtered out.

`emit.py` reads those JSON lines and maps them to BlueFlow Asset fields. For this prototype it prints; in production this becomes the Celery upsert call.

## Example

```bash
./extract.py data/hl7.pcap | ./emit.py
```

Output:

```
--- Asset 1 ---
  mac_address:
  ip_address: 192.168.56.1
  name: AccMgr
  serial_number:
  open_ports_tcp: [59185]
  source: hl7_passive

Total: 124 records from 1 device(s)
```

## Field Mapping

| Extract field | Source | Asset field |
|---|---|---|
| `mac_address` | tshark (Ethernet headers) | `mac_address` |
| `ip_address` | tcpflow filename | `ip_address` |
| `port` | tcpflow filename | `open_ports_tcp` |
| `sending_app` | MSH-3 | `name` |
| `equipment_id` | OBX-18 | `serial_number` |

## Files

```
spikes/hl7/
  extract.py    # pcap -> JSON lines (capture + parse + enrich)
  emit.py       # JSON lines -> Asset-shaped output
  docs/         # spike writeup
  data/         # sample pcap (hl7.pcap)
```
