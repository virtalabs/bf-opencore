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

### Step 1: Extract streams and MAC map from a pcap

```bash
./capture.sh <pcap_file> <output_dir>
```

Runs two tools against the same pcap:

| Tool | Job | Output |
|---|---|---|
| `tcpflow` | TCP stream reassembly (L4/L7) | One file per connection tuple |
| `tshark` | MAC-IP mapping (L2/L3) | `mac_map.tsv` |

### Step 2: Parse HL7 messages from a stream

```bash
cat <output_dir>/<stream_file> | python sender.py [--mac-map <mac_map.tsv>] [--source-ip <ip>]
```

Reads MLLP-framed HL7 messages from stdin, parses MSH/PV1/OBX segments into an `HL7Message` dataclass, and optionally enriches with MAC/IP from the capture layer.

## Example

```bash
./capture.sh data/hl7.pcap /tmp/hl7-streams

cat /tmp/hl7-streams/192.168.056.001.59185-192.168.056.001.42042 \
    | python sender.py --mac-map /tmp/hl7-streams/mac_map.tsv --source-ip 192.168.56.1
```

Output:

```
--- Message 1 ---
  mac_address: aa:bb:cc:dd:ee:ff
  ip_address: 192.168.56.1
  sending_app: AccMgr
  sending_facility: 1
  receiving_app:
  receiving_facility:
  message_timestamp: 20060302120610
  message_type: ADT^A31
  message_id: 603261
  hl7_version: 2.3.1
  patient_location:
  equipment_id:

Total: 124 messages
```

## Extracted Fields

| HL7Message field | Source | Future Asset field |
|---|---|---|
| `mac_address` | tshark MAC map | `mac_address` |
| `ip_address` | tcpflow filename / CLI arg | `ip_address` |
| `sending_app` | MSH-3 | `name` |
| `sending_facility` | MSH-4 | -- |
| `equipment_id` | OBX-18 | `serial_number` |
| `message_type` | MSH-9 | `category` (inferred) |
| `patient_location` | PV1-3 | -- |

## Files

```
spikes/hl7/
  capture.sh    # pcap -> streams + MAC map
  sender.py     # stream -> parsed HL7 messages
  docs/         # spike writeup
  data/         # sample pcap (hl7.pcap)
```
