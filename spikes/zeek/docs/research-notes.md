# Phase 1: Research Notes

## 1.1 HL7/MLLP Analyzer Assessment

### Existing analyzers

**No existing HL7 or MLLP analyzer exists for Zeek.** Searched:

- **packages.zeek.org** — No results for HL7, MLLP, healthcare, or medical. The
  closest healthcare-adjacent work is a community DICOM analyzer (relevant to #44
  but not this spike).
- **GitHub** — No maintained repositories for `zeek-hl7`, `zeek-mllp`, `spicy-hl7`,
  or `spicy-mllp`. Some academic papers reference HL7 detection via Zeek scripts
  but no published reusable code.

### Custom analysis paths

**Path A — Zeek scripting (`tcp_contents` event):**

Viable but fragile. The `tcp_contents` event fires for every TCP payload chunk and
exposes raw bytes. MLLP framing detection (`\x0b` start, `\x1c\x0d` end) is
straightforward on port 2575. Caveats:

- Must handle TCP reassembly manually — a single HL7 message may span multiple
  `tcp_contents` events
- Port-based filtering required to limit scope
- No Zeek-native protocol semantics (connection state, error handling)

Good for a quick proof-of-concept; not recommended for production.

**Path B — Spicy MLLP analyzer (recommended):**

Highly feasible. MLLP is trivially simple — no negotiation, no versioning, no
complex state machine:

```
Frame = 0x0B + HL7_payload + 0x1C + 0x0D
```

Estimated effort: ~15-30 lines of Spicy grammar, 1-2 days including the companion
`.evt` and `.zeek` files. The standard structure is:

- `.spicy` file — grammar definition
- `.evt` file — maps Spicy types to Zeek events
- `.zeek` script — defines log columns, writes `hl7.log`

**Best template:** `spicy-tftp` in the `zeek/spicy-analyzers` repository. TFTP has
similarly simple framing and is well-documented. MLLP is simpler than TFTP.

### Assessment summary

| Source | HL7/MLLP Content | Status |
|---|---|---|
| packages.zeek.org | None | Gap |
| GitHub | No maintained projects | Gap |
| `tcp_contents` scripting | Usable for quick detection | Viable but fragile |
| Spicy custom grammar | ~15-30 lines | **Best path forward** |

**Recommendation for Phase 2:** Write a custom Spicy MLLP analyzer using `spicy-tftp`
as a template. Fall back to `tcp_contents` scripting only if Spicy tooling proves
problematic on the dev environment.

---

## 1.2 Zeek Logs vs. BlueFlow Asset Fields

### Asset model fields available for mapping

From the BlueFlow Asset model, the fields most relevant to passive capture are:

| Asset Field | Type | Current Source (#47) |
|---|---|---|
| `ip_address` | InetAddressField | tcpflow (from pcap IP headers) |
| `mac_address` | MACAddressField (unique) | tshark (from pcap Ethernet frames) |
| `hostname` | TextField | **Gap** — needs DNS reverse lookup |
| `name` | CharField | MSH-3 (sending_app) |
| `manufacturer` | TextField | **Gap** — MSH-3 unreliable |
| `nic_vendor` | TextField | Auto-populated from OUI on save |
| `model` | TextField | **Gap** — not in HL7 v2.x |
| `serial_number` | TextField | OBX-18 (equipment_id, ~30-50% coverage) |
| `os` | TextField | **Gap** — needs TCP fingerprinting |
| `open_ports_tcp` | ArrayField[int] | MLLP port (from pcap) |
| `external_keys` | JSONField | HL7 context fields (MSH-4/5/6/7/9/10/12, PV1-3) |

### What emit.py currently produces

The #47 pipeline maps 5 core Asset fields (`mac_address`, `ip_address`, `name`,
`serial_number`, `open_ports_tcp`) plus HL7 context fields (sender/receiver pairs,
timestamps, message types) stored in `external_keys` or custom fields.

### Zeek log mapping

| Zeek Log | BlueFlow Field(s) | Closes #47 Gap? | Assessment |
|---|---|---|---|
| `conn.log` | `ip_address`, `open_ports_tcp`, topology edges | No — already covered by tcpflow | Provides richer data: connection duration, byte counts, protocol detection. Topology edges (IP pairs + ports) are a direct upgrade over MSH-3/MSH-5 inference from #47 Section 6. |
| `dns.log` | `hostname` | **Yes** — closes the DNS gap | Zeek passively logs all DNS queries/responses on the monitored segment. Maps `ip_address` → `hostname` without active reverse lookups. This was identified as a gap in #47. |
| `dhcp.log` | `mac_address` ↔ `ip_address` binding | **Partially** — reduces tshark dependency | Logs DHCP transactions including MAC, assigned IP, and hostname. Covers devices that use DHCP. Static-IP devices (common in medical equipment) will not appear — tshark Ethernet frame extraction may still be needed as a fallback. |
| `ssl.log` | `manufacturer` (from cert CN/SAN/issuer) | **Partially** — new data source | TLS certificate metadata (CN, SAN, issuer, validity) provides device/manufacturer identification not available from HL7. Only covers TLS-enabled connections. Does **not** decrypt TLS-wrapped MLLP — the "TLS blindness" problem remains. |
| `known_hosts.log` | Entity resolution / deduplication | No new fields | Deduplicated host tracking — natural fit for asset entity resolution. Provides first-seen/last-seen timestamps. |
| `known_services.log` | `open_ports_tcp`, service identification | Supplements nmap | Service fingerprinting overlaps with nmap but works passively. Useful for detecting services nmap doesn't scan for. |

### Key finding: dhcp.log and the MAC-IP gap

The #47 spike identified `mac_address` as the primary lookup key for asset upsert,
and tshark as the only way to extract MAC-IP bindings from pcap. Zeek's `dhcp.log`
provides MAC-IP correlation for DHCP-using devices, but **static-IP medical devices
(monitors, infusion pumps, imaging systems) will not appear in DHCP logs**. This
means tshark remains necessary as a fallback for complete MAC coverage.

However, Zeek's `conn.log` does record the `orig_l2_addr` and `resp_l2_addr` fields
(MAC addresses of connection endpoints) when Zeek monitors a live interface — this
would eliminate the tshark dependency entirely in live-capture mode. These fields are
**not populated when reading from pcap** (no Ethernet headers in tcpdump-style
captures unless captured with `-e`).

### Net new data from Zeek (not available in #47 pipeline)

1. **DNS hostname resolution** — fills the `hostname` gap
2. **TLS certificate metadata** — new source for `manufacturer` identification
3. **Connection metadata** — duration, byte counts, protocol detection
4. **Service fingerprinting** — passive alternative to nmap for port/service discovery
5. **Topology edges** — richer than MSH-3/MSH-5 inference

---

## 1.3 Deployment Viability

### Resource footprint

Zeek is single-threaded per worker process. For ~500 devices on a link under
100 Mbps (typical for a 25-bed hospital LAN):

| Resource | Idle | Under Load | Notes |
|---|---|---|---|
| CPU | Near zero | **1 core** | Sizing rule: ~1 core per 250 Mbps |
| Memory | 200-500 MB | **1-2 GB** | Single worker process |
| Disk | — | **1-5 GB/day** | TSV logs; ~10:1 compression ratio |

Community FAQ confirms small deployments (under 1 Gbps) run on commodity hardware
(4 cores, 8 GB RAM). 100 GB disk partition gives weeks of log retention.

### Installation paths

| Method | Available? | Notes |
|---|---|---|
| `apt install zeek` | Yes, via OBS repo | Not in default repos. Zeek provides an official OpenBuildService repository. Packages for Debian 11/12, Ubuntu 22.04/24.04. |
| `brew install zeek` | Yes, Homebrew core | Good for dev/testing, not production. |
| Docker (`zeek/zeek`) | Yes, Docker Hub | Official images available. Adds overhead to raw socket access — bare-metal/VM preferred for production packet capture. |

### Operational complexity

**Zeek (daemon model):**
- `zeekctl deploy` after config changes
- `zeekctl status` to check health
- Cron job runs `zeekctl cron` every 5 minutes (crash restart + log rotation)
- Persistent daemon — must be monitored and managed

**tcpflow (periodic invocation):**
- Run via cron against rotated pcap files
- No daemon, no state management
- Simpler but provides only flow reconstruction — no protocol analysis

**Verdict:** Zeek is operationally heavier but the structured protocol logs (DNS,
HTTP, TLS, DHCP) are a substantial upgrade over raw flow data. For a product that
already manages PostgreSQL, Redis, and Celery, adding one more daemon is incremental.

### Single-box deployment

Zeek can coexist on the same VM as Django/PostgreSQL/Redis/Celery. No known port
conflicts or library incompatibilities. Recommended minimum for combined deployment:

- **4 cores, 8 GB RAM** for BlueFlow + Zeek on a 500-device network
- Pin Zeek to specific cores via `zeekctl` CPU affinity if needed
- Separate the capture interface from the management interface serving the web app

### Cluster mode

Not needed for small deployments. Cluster mode (multiple workers, proxy, manager)
is for multi-gigabit links. Standalone single-process is sufficient.

### Licensing

Zeek is **BSD 3-Clause licensed** (confirmed in `zeek/zeek` repo, `COPYING` file).
Free for commercial and non-commercial use. No copyleft obligations. Compatible
with BlueFlow's deployment model.
