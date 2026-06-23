# Topograph Spike — Findings

## What the spike accomplishes

### Directed graph model validated

This spike proves that a network topology can be represented as a directed graph of `TopologyNode` objects linked by `ServiceEdge` tuples `(peer_node, port, service, protocol)`. Edges are stored as `outbound` on the initiating node and `inbound` on the receiving node. This is intended to allow consumers to traverse either direction independently. Note that intermediates are not modelled. There should be more discussion with consumers on producer expectations around path analysis. For example, maybe we begin with consumer derived BFS and aim for providing per-hop service paths (See follow-up 4).

### MAC-anchored identity

Each node's `node_id` is the primary MAC address, giving hardware-stable identity that survives hostname changes. Where no MAC is present, a synthetic one is derived from the IP address so the graph remains a valid keyed dict at the cost of stability.

### Subnet-scoped reachability

The builder groups nodes by `/24` subnet and infers directed edges only within a subnet. This produces a conservative, defensible reachability model: two nodes are considered able to communicate only if they share a broadcast domain. The output for `demo1` correctly isolates `10.10.1.0/24` (clinical VLAN) from `10.10.0.0/24` (edge VLAN).

### Service inference from device class

`registries.py` encodes two static maps:

- `PORT_SERVICE_MAP` — port → `(service_name, protocol)`, covering IT, OT/ICS, and medical protocol ports (DICOM, HL7, WS-Discovery, Modbus, OPC-UA, BACnet, etc.)
- `DEVICE_CLASS_INITIATES` — device class → frozenset of services the class initiates outbound

Edge inference applies the rule: if node A's class initiates service S, and node B exposes a port that resolves to S, emit `A → B` on S. Wildcard (`"*"`) covers routers, firewalls, and gateways, which can initiate any service. This gives plausible edges from a passive asset inventory without requiring observed connection data.

### Working fixture

`fixtures/topology/demo1/` provides a seven-node, two-VLAN scenario (Philips clinical devices + Palo Alto firewall + Cisco gateway + Epic EHR edge server) with a committed output in `results/topology_graph.json`. The fixture exercises patient monitors, imaging systems, clinical workstations, PACS servers, networking devices, and an EHR server across two subnets. It can serve as the seed for the `0.1.0-minimal` example payload required by #135.

### Schema shape established

The `to_dict()` output (`TopologyGraph`, `TopologyNode`, `ServiceEdge`) defines a concrete JSON shape that can be transcribed into a JSON Schema artifact. The shape is:

```json
{
  "subnets": ["10.10.0.0/24", "10.10.1.0/24"],
  "nodes": [
    {
      "node_id": "<MAC>",
      "hostname": "...",
      "vendor": "...",
      "product": "...",
      "version": "...",
      "device_class": "...",
      "interfaces": [{ "mac": "...", "ip": "...", "subnet": "..." }],
      "subnets": ["..."],
      "inbound": [
        {
          "from_node": "<MAC>",
          "port": 0,
          "service": "...",
          "protocol": "tcp|udp"
        }
      ],
      "outbound": [
        {
          "to_node": "<MAC>",
          "port": 0,
          "service": "...",
          "protocol": "tcp|udp"
        }
      ]
    }
  ]
}
```

---

## Gaps and follow-up items for issue #135

### 1. Identity anchor conflict

The spike uses MAC as `node_id` (primary identity). Issue #135, via the #144 prerequisite, mandates `asset.id = Asset.hostname`. These differ in stability and should be reassessed based on consumer feedback (Hawksbill, Galois, Viper)

**Follow-up:** Before committing the schema artifact, pin which field is the canonical `id` in `0.1.0-minimal`. One resolution is to surface hostname as `id` (satisfying #135's AC) and retain MAC inside `interfaces` for hardware correlation.

---

### 2. No schema artifact committed

The spike produces JSON output but no `0.1.0-minimal.json` schema file exists. The #135 AC requires a committed artifact at `blueflow/contracts/topology/0.1.0-minimal.json` and an OpenAPI reference to the same version string.

**Follow-up:** After consumer/stakeholder feedback, author the JSON Schema from the spike's `to_dict()` shape, add the required API envelope fields (see item 3), etc.

---

### 3. API envelope fields are absent

The spike output has no `schema_version`, `snapshot_id`, or `timestamp` at the root level. These are required by the #135 endpoint AC: _"Response includes required root fields (`schema_version`, `snapshot_id`, `timestamp`, `assets`)"_.

**Follow-up:** Wrap `TopologyGraph.to_dict()` in an envelope before it leaves the view:

```json
{
  "schema_version": "0.1.0-minimal",
  "snapshot_id": "<uuid>",
  "timestamp": "<ISO-8601>",
  "subnets": [...],
  "nodes": [...]
}
```

### 4. `connections` shape is unresolved

The spike encodes edges as `inbound`/`outbound` lists on each node. The #135 AC references "≥1 connection" as a fixture requirement but does not specify whether the schema exposes a flat top-level `connections` list alongside (or instead of) per-node edge lists.

**Follow-up:** Decide and document the `connections` shape, if at all, before the API is committed and mocked. Suggested options:

- **Per-node only** sufficient for graph traversal, less convenient for consumers doing bulk edge queries.
- **Flat `connections` list at root** — `[{from_node, to_node, port, service, protocol}]` is a simple example; removes the need to deduplicate symmetric edges.
- **Both** — flat list for consumers, per-node edges for rendering.

---

### 5. Cross-subnet edges are absent

`builder._infer_edges` only connects nodes sharing a subnet (`builder.py:110`). In `demo1`, the firewall (`10.10.0.1`) and the clinical workstation (`10.10.1.31`) are on different VLANs, so no edge exists between them. A multi-hop attack path that traverses the firewall into the clinical VLAN cannot be expressed in the current graph.

**Follow-up:** Model inter-subnet reachability by treating devices with wildcard initiation (routers, firewalls, gateways) as routing nodes that can bridge subnets. The approach depends on whether `NetworkEndpoint` in blueflow carries interface-level subnet data or only a single IP. This is not a blocker for the minimal endpoint but is a prerequisite for attack path (PoE) use cases to produce meaningful results on real ranges.

---

### 6. No mapping from `Asset`/`NetworkEndpoint` to `TopologyNode`

The spike reads flat TapirXL JSON dicts. The production implementation must query Django `Asset` and `NetworkEndpoint` models. No translation layer exists. The #135 AC explicitly requires: _"Reuse existing models (`Asset`, `NetworkEndpoint`); no new topology models"_.

**Follow-up:**

- Is this AC still appropriate?
- Does `NetworkEndpoint` carry observed open-port data, or only protocol/service assignments? If observed ports are available, the static `DEVICE_CLASS_INITIATES` registry becomes a fallback rather than the primary inference mechanism.
- How are multi-homed devices (multiple `NetworkEndpoint` rows per `Asset`) represented? The spike builds one `NetworkInterface` per asset; production may need to aggregate.
- Does `Asset.hostname` uniqueness hold, or can duplicates exist? The #135 AC says assets with null/empty hostnames are excluded; duplicate-hostname behavior needs to be documented.

---

### 7. Broadcast and multicast protocols not distinguished from unicast

The schema's directed edge model assumes point-to-point unicast communication. Broadcast and multicast protocols (device discovery, time sync, group streaming) do not have a single destination node and cannot be accurately represented as a directed `(src, dst)` edge. `PORT_SERVICE_MAP` currently makes no distinction between unicast and non-unicast services, so any port that maps to a multicast/broadcast protocol could produce spurious directed edges if a future device class entry initiates it.

**Follow-up:** Introduce a protocol topology category like `unicast` vs. `non-unicast` flag on `PORT_SERVICE_MAP` entries, and exclude non-unicast services from directed edge inference. Non-unicast services may warrant a separate representation in the schema (e.g., a `broadcasts` list on the node) to preserve the observability data without misrepresenting it as a point-to-point connection.

---

### 8. `_open_ports` stored via dict mutation

**Gap:** `builder.py:98` `node.__dict__["_open_ports"] = open_ports` stashes transient builder state on a dataclass instance via direct dict manipulation. This bypasses the dataclass contract and is fragile.

**Follow-up:** If the builder pattern is carried forward into production, either add `_open_ports` as a proper (excluded) dataclass field or keep open ports in the builder's own state dict keyed by `node_id` rather than attaching them to the node.
