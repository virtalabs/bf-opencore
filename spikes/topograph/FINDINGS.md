# Topograph Spike — Findings

## What the spike accomplishes

The Python graph builder (`models.py`, `builder.py`, `registries.py`) proves that a network topology can be represented as a directed graph. Edges are stored as `outbound` on the initiating node and `inbound` on the receiving node, allowing consumers to traverse either direction independently. Intermediates are not modelled.

**Note:** The spike's internal JSON shape (MAC-anchored `node_id`, embedded `inbound`/`outbound` lists, TapirXL field names) informed API design but is **not** the wire format. The contract lives in [`openapi.yaml`](openapi.yaml) and diverges intentionally. See below.

### Directed graph model validated

`TopologyNode` objects are linked by `ServiceEdge` tuples `(peer_node, port, service, protocol)`.

### MAC-anchored identity (spike internal only)

Each node's `node_id` is the primary MAC address. Where no MAC is present, a synthetic one is derived from the IP address.

### Subnet-scoped reachability

The builder groups nodes by `/24` subnet and infers directed edges only within a subnet. The `demo1` fixture isolates `10.10.1.0/24` (clinical VLAN) from `10.10.0.0/24` (edge VLAN).

### Service inference from device class

`registries.py` encodes:

- `PORT_SERVICE_MAP`: port → `(service_name, protocol)`
- `DEVICE_CLASS_INITIATES`: device class → frozenset of services the class initiates outbound

Edge inference: if node A's class initiates service S, and node B exposes a port that resolves to S, emit `A → B` on S. Wildcard (`"*"`) covers routers, firewalls, and gateways.

### Working fixture

`fixtures/topology/demo1/` provides a seven-node, two-VLAN scenario with committed output in `results/topology_graph.json`.

---

## API contract design decisions (`0.1.0-minimal`)

Artifact: [`spikes/topograph/openapi.yaml`](openapi.yaml). Spike-only for now; promote to `blueflow/contracts/topology/` at implementation time.

| Topic                   | Decision                                                                                                                                                                                                             |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Envelope**            | `schema_version`, `snapshot_id`, `timestamp`, `assets[]`; optional `connections[]`, `external_endpoints[]`, `query`, `networks[]`                                                                                    |
| **Graph shape**         | Canonical flat list: nodes (`assets`) + edges (`connections`), not per-node `inbound`/`outbound`                                                                                                                     |
| **Asset identity**      | `id` = integer `Asset.id` (PK); `hostname` separate, nullable                                                                                                                                                        |
| **Asset fields**        | Mirror Blueflow `Asset` API surface: `manufacturer`, `model`, `category`, `app_sw_version` — open strings, trust upstream producer vocabularies (TapirXL `device_class` → `category` at ingest)                      |
| **Interface**           | No `id`; `mac_address`, `ipv4_address`, `ipv6_address` only                                                                                                                                                          |
| **Services**            | `(port, protocol, service)` open strings; `cast` enum (`unicast`/`multicast`/`broadcast`); non-unicast excluded from `connections[]`                                                                                 |
| **Connection**          | Address-only flow tuple: `src_ip`, `dst_ip`, `dst_port`, `protocol`, `response_observed`, `service` — no asset IDs or hostnames on the edge                                                                          |
| **External peers**      | Off-inventory endpoints in `external_endpoints[]` (`ip_address`, optional `hostname`); referenced by `src_ip`/`dst_ip` in connections                                                                                |
| **CIDR filtering**      | Query params `cidr` (repeatable), `network`, `edge_scope` (`internal`/`boundary`); response echoes `query`, per-CIDR `networks` rollup, `matched_cidrs` + `in_scope` on assets                                       |
| **Path**                | `GET /topology` (no trailing slash)                                                                                                                                                                                  |
| **Auth**                | DRF token auth (`Authorization: Token <key>`)                                                                                                                                                                        |
| **`response_observed`** | `true` = return traffic seen; `false` = initiation seen, no reply (full visibility); `null` = unknown (partial span, sampling, or inferred edge). Not derivable from TapirXL inventory or current Zeek→Asset ingest. |
| **Mocking**             | See **Mocking** section below                                                                                                                                                                                        |

Example connection:

```yaml
- src_ip: 10.10.1.31
  dst_ip: 10.10.1.41
  dst_port: 104
  protocol: tcp
  response_observed: true
  service: dicom
```

---

## Gaps and follow-up items

### Resolved (superseded)

| #   | Original gap                               | Resolution                                                |
| --- | ------------------------------------------ | --------------------------------------------------------- |
| 1   | Identity anchor conflict (MAC vs hostname) | Integer `Asset.id` + separate nullable `hostname`         |
| 2   | No schema artifact                         | OpenAPI 3.1 spec                                          |
| 3   | API envelope fields absent                 | Defined in spec                                           |
| 4   | `connections` shape unresolved             | Flat `connections[]` at root                              |
| 7   | Broadcast/multicast not distinguished      | `Service.cast`; non-unicast excluded from `connections[]` |

### Open

**# Cross-subnet edges**

`builder._infer_edges` only connects nodes sharing a subnet. CIDR filtering + `edge_scope=boundary` partially addresses consumer needs for multi-segment views. Routing-node inference (firewalls/gateways bridging VLANs) is still TBD for attack-path use cases.

**#6 No mapping from `Asset`/`NetworkEndpoint` to topology wire shape**

Reframed as an implementation task, not a contract blocker. Production must query `Asset` (and interfaces derived from `NetworkEndpoint` or asset IP fields), materialize `connections[]` from observed flows, and optionally fall back to class+port inference with `response_observed: null`.

Open questions:

- Multi-homed devices: aggregate multiple interface IPs per asset.
- `Asset.hostname` nullability and duplicate-hostname behavior at materialization time.

**#8 `_open_ports` stored via dict mutation**

`builder.py` stashes transient state on dataclass instances via `node.__dict__["_open_ports"]`. If the builder is reused in production inference, move open ports to builder-local state or a proper excluded field.

---

## Implementation next steps

### Flow table (new persistence)

Flows are not asset attributes. Blueflow needs a dedicated **`ObservedFlow`** model (name TBD):

```
(src_ip, dst_ip, dst_port, protocol)  -- natural key within retention window
response_observed   bool | null
visibility          full | partial | egress_only | sampled
first_seen, last_seen
evidence            JSON  -- conn_state, history, orig_bytes, resp_bytes
provenance          zeek | tapirxl | netflow
```

Snapshot materialization: aggregate flows in a time window → emit `connections[]`; resolve IPs against asset interfaces or `external_endpoints[]`; inferred edges (class+port rules) get `response_observed: null`.

### Zeek ingest extension

Current [`blueflow/zeek/sidecar.py`](../../blueflow/zeek/sidecar.py) reads `conn.log` but only extracts endpoint identity and responder `open_ports_tcp`. Extend to emit flow records using fields already in Zeek:

| Flow field                                 | Zeek source                                                                 |
| ------------------------------------------ | --------------------------------------------------------------------------- |
| `src_ip`, `dst_ip`, `dst_port`, `protocol` | `id.orig_h`, `id.resp_h`, `id.resp_p`, `proto`                              |
| `response_observed`                        | Derive from `history`, `conn_state`, `orig_bytes`, `resp_bytes`             |
| `evidence`                                 | Store raw conn record subset                                                |
| `visibility`                               | Set from span metadata when available; default `full` for single-tap ingest |

Wire into a new flow ingest path (extend `zeek_ingest` or a separate management command). See [`blueflow/zeek/README.md`](../../blueflow/zeek/README.md) for the current Asset-only field mapping.

### Production promotion checklist

When moving from spike to implementation:

1. Promote `openapi.yaml` → `blueflow/contracts/topology/openapi.yaml`
2. Align [`blueflow/views/topology.py`](../../blueflow/views/topology.py) serializers with contract (currently stale: hostname-as-id, `direction` enum, no `external_endpoints`, interface string ids)
3. Implement snapshot builder querying `Asset`, `NetworkEndpoint`, `ObservedFlow`
4. Add contract tests / Spectral lint in CI

---

## Mocking

Run either mock server against [`openapi.yaml`](openapi.yaml) from the repo root. All requests require `Authorization: Token <key>`.

### Prism

```bash
npx @stoplight/prism-cli mock spikes/topograph/openapi.yaml -p 4010
curl -H "Authorization: Token x" http://127.0.0.1:4010/topology
```

Request a named example:

```bash
curl -H "Authorization: Token x" \
  -H "Prefer: example=filtered_multi_cidr" \
  http://127.0.0.1:4010/topology
```

### Scalar

```bash
docker run --rm -p 4010:3000 \
  -v "$(pwd)/spikes/topograph/openapi.yaml:/docs/openapi.yaml:ro" \
  scalarapi/mock-server:latest
curl -H "Authorization: Token x" http://127.0.0.1:4010/topology
```

Scalar UI: `http://localhost:4010/scalar`. Spec: `/openapi.yaml`.
