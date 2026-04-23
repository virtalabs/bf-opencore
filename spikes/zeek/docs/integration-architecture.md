# Integration Architecture

## Constraints

- Zeek probes may be **remote** — not co-located with BlueFlow.
- A deployment may have **multiple probes**, each monitoring a different network
  segment.
- Probes are **stateless data sources**; BlueFlow is the single source of truth.

## Existing upsert endpoint

BlueFlow already has `PUT /api/assets/upsert/` (in `blueflow/views/asset.py`)
designed for passive scanners. It:

- Upserts by `mac_address` (create if new, update if exists)
- Accepts the fields a probe would send: `ip_address`, `name`, `hostname`,
  `manufacturer`, `model`, `serial_number`, `os`, `category`, `external_keys`,
  `open_ports_tcp`
- Merges `open_ports_tcp` (union of existing + new, sorted and deduped)
- Records provenance via `client_id`, `provenance`, and `last_seen` in the
  `simple_history` audit trail
- Uses token auth

The probe integration should build on this endpoint rather than introduce a
parallel ingest API. The probe-side sidecar is responsible for transforming
Zeek log entries into asset-shaped upsert payloads.

## Data flow

```
┌──────────┐   logs   ┌──────────┐  PUT /api/assets/upsert/  ┌───────────┐
│   Zeek   │ ───────> │ Sidecar  │ ────────────────────────> │ BlueFlow  │
│  (probe) │          │ (Python) │   one request per asset    │   API     │
└──────────┘          └──────────┘                            └───────────┘
```

The sidecar correlates Zeek's per-log-type entries (`hl7.log`, `conn.log`,
`dns.log`, `ssl.log`) into per-asset observations before pushing. BlueFlow
receives asset-shaped payloads — it does not need to understand Zeek log
formats.

## Zeek output options

Zeek is not limited to writing files. The choice of output mechanism determines
how the sidecar consumes data:

| Output mechanism | How it works | Sidecar reads from | Dependencies |
|---|---|---|---|
| **Log files (JSON)** | Zeek writes JSON to disk, sidecar tails files | File system | None — Zeek default with `LogAscii::use_json = T` |
| **Broker framework** | Zeek publishes log records via native pub/sub, sidecar subscribes | Broker socket | `broker` Python package; Zeek configured with Broker listener |
| **Kafka log writer** | Zeek plugin replaces file writer with Kafka producer | Kafka topic | `zeek-kafka` plugin + Kafka cluster |
| **ActiveHTTP** | Zeek script makes HTTP calls per event | N/A (no sidecar) | Nothing extra, but no batching, retry, or correlation |

### Recommended: file tail (initial), Broker (upgrade path)

**File tail** for initial implementation:

- Zeek already writes log files — no configuration changes needed beyond
  enabling JSON format (`LogAscii::use_json = T`)
- Log files are inspectable for debugging — you can always `cat hl7.log`
- The sidecar is a small Python script that watches for new lines, correlates
  by IP/MAC, and PUTs to the upsert endpoint
- Works on every Zeek deployment regardless of version or plugins

**Broker** as the upgrade path when file management becomes a pain:

- Eliminates intermediate files — sidecar subscribes directly to Zeek's log
  stream over a socket
- Lower latency than file tailing
- Requires the `broker` Python package on the probe host and Zeek configured
  to accept Broker connections
- Good fit when probes are on reliable local networks

**Kafka** is viable at scale but adds infrastructure (a broker cluster) that is
premature for small hospital deployments. **ActiveHTTP** lacks batching, retry,
and cross-log correlation — not suitable as the primary integration path.

## Sidecar responsibilities

The sidecar runs on the same host as Zeek and is the only component that
understands Zeek log formats. Its job:

1. **Consume** Zeek log entries (via file tail or Broker subscription)
2. **Correlate** entries across log types into per-asset observations:
   - `conn.log` provides `ip_address`, `open_ports_tcp`, `mac_address` (live
     capture only, from `orig_l2_addr` / `resp_l2_addr`)
   - `hl7.log` provides `name` (MSH-3), `serial_number` (OBX-18),
     `external_keys` (MSH context fields)
   - `dns.log` provides `hostname`
   - `ssl.log` provides `manufacturer` hints (cert CN/issuer)
3. **Push** correlated asset payloads to `PUT /api/assets/upsert/`
4. **Send heartbeats** on a configurable interval (see liveness monitoring)

### Upsert payload shape

The sidecar produces payloads matching the existing `AssetUpsertSerializer`:

```json
{
  "mac_address": "00:1a:2b:3c:4d:5e",
  "ip_address": "10.1.4.20",
  "name": "AccMgr",
  "hostname": "admit-mgr.hospital.local",
  "open_ports_tcp": [2575],
  "external_keys": {
    "hl7_sending_facility": "1",
    "hl7_message_types": ["ADT^A01", "ADT^A31", "ADT^A04"],
    "hl7_version": "2.3.1"
  },
  "client_id": "zeek-probe-site-a-01",
  "provenance": "Zeek"
}
```

The existing endpoint handles the rest: create-or-update by MAC, merge ports,
record history with provenance.

### MAC address availability

Zeek `conn.log` L2 fields (`orig_l2_addr`, `resp_l2_addr`) only populate in
live capture mode — not during pcap replay. The sidecar must handle two cases:

- **MAC available (live capture):** Use `mac_address` as the upsert key
  (matches existing endpoint behavior).
- **MAC unavailable (pcap replay / no L2 visibility):** Fall back to IP-only.
  This is a gap in the current upsert endpoint, which requires `mac_address`.
  A future enhancement could allow upsert by IP when MAC is unknown.

## Multi-probe concerns

### Probe identity

Each probe identifies itself via the `client_id` field on upsert requests
(e.g. `zeek-probe-site-a-01`). This is already recorded in the
`simple_history` audit trail — no new model needed for the initial
implementation.

For probes monitoring different sites with overlapping RFC1918 space, the
`client_id` provides attribution but does not resolve address ambiguity.
A future `ProbeRegistration` model associating `client_id` with a
Network/CIDR would address this.

### Deduplication

Overlapping probes (two probes mirroring the same span port) will produce
duplicate upsert calls for the same asset. The existing endpoint is
naturally idempotent for most fields (setting `name` to the same value is a
no-op at the application level). Port merging is also idempotent (union).

For HL7 `external_keys`, the sidecar should deduplicate by MSH-10 (message
control ID) + timestamp before pushing, to avoid redundant history entries.

### Liveness monitoring

A probe that stops sending could mean the network is quiet, the probe
crashed, or the network path is down. Strategy: the sidecar sends periodic
heartbeat requests on a configurable interval (default: 60s). BlueFlow
alerts if a probe misses 3 consecutive heartbeats.

The heartbeat can be a lightweight `PUT /api/assets/upsert/` with only
the probe's own MAC and `client_id`, or a dedicated health endpoint if
the overhead of upsert is undesirable.

## Docker Compose validation

The full pipeline was validated using a 3-container Docker Compose setup
(`docker-compose.yml`):

- **traffic** — replays the sample pcap via `tcpreplay` over a veth pair
- **zeek** — live-captures on the veth pair, compiles the Spicy MLLP analyzer,
  runs the sidecar to push to blueflow
- **blueflow** — stub HTTP server that accepts any PUT and returns 200

### Key findings from containerized testing

1. **Raw IP pcap framing** — The sample pcap uses `DLT_RAW` (captured on
   loopback). Veth pairs are Ethernet interfaces (`DLT_EN10MB`), so a
   conversion step (`raw2enet.py`) wraps each packet in an Ethernet frame.
   Production probes doing live capture would not need this step — they already
   see Ethernet-framed traffic.

2. **Veth pair for in-container capture** — Docker bridge networks are switched;
   containers only see traffic destined for them. Sharing a network namespace
   between the traffic generator and Zeek, then using a veth pair for packet
   injection, gives Zeek proper incoming traffic to capture.

3. **End-to-end result** — 503 packets replayed, Zeek extracted 124 HL7
   messages (matching the #47 baseline), sidecar aggregated into 1 asset,
   upsert payload reached the stub server with correct fields.

4. **Deduplication gap** — The sidecar does not yet deduplicate by MSH-10
   message control ID + timestamp. It aggregates all entries into per-device
   payloads without tracking seen messages. For overlapping probes, this would
   produce redundant `external_keys` data and unnecessary history entries in
   BlueFlow. The `message_id` field is already extracted by Zeek and available
   in the sidecar — the dedup logic just needs to be added to `aggregate()`.

## Relationship with active MLLP endpoint (FY2027)

The passive Zeek probe and a future active MLLP endpoint (BlueFlow listening
on port 2575 for direct HL7 feeds) share the same downstream processing:

- Both produce HL7 message fields (MSH, PID, PV1, OBX segments).
- Both need to upsert assets and populate `external_keys`.

The sidecar's HL7 field extraction logic and the future MLLP receiver should
share a common utility (e.g. `blueflow/utils/hl7.py`). The #47 spike's
`extract.py` is the starting point for this shared layer.
