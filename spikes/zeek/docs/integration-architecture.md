# Integration Architecture

## Constraints

- Zeek probes may be **remote** — not co-located with BlueFlow.
- A deployment may have **multiple probes**, each monitoring a different network
  segment.
- Probes are **stateless data sources**; BlueFlow is the single source of truth.

## Data flow options

| Option | Remote? | Multi-probe? | New infra? | Assessment |
|---|---|---|---|---|
| File polling | Needs shared FS (NFS) | Awkward | No | **Eliminated** — fragile across hosts, no native multi-probe story |
| Named pipe | Same-host only | No | No | **Eliminated** — violates remote constraint |
| HTTP push | Yes | Yes | No | **Recommended** — each probe POSTs to BlueFlow API |
| Message queue | Yes | Yes | Broker (Kafka/Redis streams) | Viable at scale, premature for small hospitals |

## Recommended approach: HTTP push

Each probe pushes structured log data to BlueFlow's existing DRF API over HTTP.

```
┌──────────┐     HTTPS POST      ┌───────────┐     Celery      ┌────────────┐
│  Zeek    │ ──────────────────> │  BlueFlow │ ─────────────> │ PostgreSQL │
│  Probe N │   /api/probe/ingest │  API      │   async task    │            │
└──────────┘                     └───────────┘                 └────────────┘
```

### Why HTTP push

- No new infrastructure — uses the existing DRF API and token auth.
- Works for 1 probe or 10 without architectural changes.
- Probes can be behind NAT or firewalls (outbound HTTPS only).
- Does not preclude adding a message broker later if scale demands it.

### Push mechanism on the probe side

Two options, in order of preference:

1. **Zeek `ActiveHTTP` module** — built-in HTTP client callable from Zeek
   scripts. The `hl7_extract.zeek` script would POST each log entry (or a
   batch) directly to the ingest endpoint. No sidecar process needed. Limited
   to simple HTTP — no retry logic or backpressure.

2. **Lightweight sidecar** — a small script (Python or shell) that tails Zeek's
   JSON log output and POSTs batches to BlueFlow. Adds retry, buffering, and
   backpressure handling. More moving parts, but more robust for unreliable
   links.

For initial implementation, start with `ActiveHTTP`. Move to a sidecar if
reliability requirements grow (e.g. probes on flaky WAN links).

### Zeek log format

Zeek must be configured with `LogAscii::use_json = T` for push-based
integration. JSON logs are self-describing and trivially parseable by the
ingest endpoint. The default TSV format (used in the prototype) is fine for
local analysis but awkward for HTTP payloads.

## Ingest endpoint

### API shape

```
POST /api/probe/ingest/
Authorization: Token <probe-api-key>
Content-Type: application/json

{
  "probe_id": "probe-site-a-01",
  "log_type": "hl7",
  "entries": [
    {
      "ts": 1468591534.681516,
      "uid": "CjIBpa4vO8otVlPiQ5",
      "id.orig_h": "10.1.4.20",
      "id.resp_h": "10.1.4.50",
      "id.resp_p": 2575,
      "sending_app": "AccMgr",
      "message_type": "ADT^A01",
      "message_id": "603262",
      ...
    }
  ]
}
```

- Batched: multiple log entries per request to reduce HTTP overhead.
- `probe_id` identifies the source probe (tied to API token on the server).
- `log_type` distinguishes HL7 entries from conn/dns/ssl entries.

### Validation

- Reject unknown `probe_id` or token mismatch.
- Reject entries without required fields (`ts`, `uid`, originator/responder).
- Accept-and-warn on entries with unknown fields (forward compatibility when
  Zeek scripts add new columns).

## Celery task interface

The ingest endpoint hands off to a Celery task for async processing:

```python
@shared_task
def process_probe_data(probe_id: str, log_type: str, entries: list[dict]):
    """
    Route probe log entries to the appropriate handler.

    - hl7: extract asset fields, upsert Asset, populate external_keys
    - conn: update open_ports_tcp, connection metadata
    - dns: resolve hostname for known assets
    - ssl: extract manufacturer hints from cert metadata
    """
```

This matches BlueFlow's existing pattern — the API validates and enqueues,
Celery does the heavy lifting. Each log type maps to an asset field update
strategy:

| Log type | Asset fields updated | Upsert key |
|---|---|---|
| `hl7` | `name`, `serial_number`, `open_ports_tcp`, `external_keys` | `ip_address` (+ `probe_id` for disambiguation) |
| `conn` | `ip_address`, `open_ports_tcp`, `mac_address` (live only) | `ip_address` |
| `dns` | `hostname` | `ip_address` |
| `ssl` | `manufacturer` (from cert CN/issuer) | `ip_address` |

## Multi-probe concerns

### Probe registration

Each probe is registered in BlueFlow with:

- **Probe ID** — unique identifier (e.g. `probe-site-a-01`)
- **API token** — for authentication
- **Network/CIDR** — the segment this probe monitors, used to disambiguate
  overlapping RFC1918 space across sites
- **Last seen** — updated on each successful ingest, used for liveness checks

This could be a lightweight model (`ProbeRegistration`) or a configuration
entry — the decision depends on whether probes need to be managed via the UI.

### Deduplication

Overlapping probes (two probes mirroring the same span port) will produce
duplicate data. Deduplication strategy:

- **HL7 messages:** Deduplicate by `(message_id, message_timestamp, probe_network)`.
  MSH-10 (message control ID) is unique per sending system.
- **Connection data:** Deduplicate by `(uid, ts)`. Zeek UIDs are unique per
  Zeek instance, so duplicates from different probes will have different UIDs —
  but the underlying connection is the same. Use the 5-tuple
  `(orig_h, orig_p, resp_h, resp_p, ts)` as the true dedup key.

### Liveness monitoring

A probe that stops sending could mean:

1. The monitored network is genuinely quiet.
2. The probe process crashed.
3. The network path between probe and BlueFlow is down.

Strategy: probes send periodic heartbeats (empty ingest with `log_type: heartbeat`)
on a configurable interval (default: 60s). BlueFlow alerts if a probe misses
3 consecutive heartbeats.

## Relationship with active MLLP endpoint (FY2027)

The passive Zeek probe and a future active MLLP endpoint (BlueFlow listening on
port 2575 for direct HL7 feeds) share the same downstream processing:

- Both produce HL7 message fields (MSH, PID, PV1, OBX segments).
- Both need to upsert assets and populate `external_keys`.

The `process_probe_data` Celery task should delegate HL7 field extraction to a
shared utility (e.g. `blueflow/utils/hl7.py`) that both the probe ingest path
and the future active MLLP receiver can call. The #47 spike's `extract.py`
logic is the starting point for this shared layer.

