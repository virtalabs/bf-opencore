# Decision Note: Zeek Evaluation (#111)

## Recommendation

**Adopt Zeek as the probe platform** for passive network capture.

Zeek should serve as a stateless, remote-capable probe that pushes structured
data to BlueFlow over HTTP. The architecture must support multiple probes per
deployment (e.g. one per network segment) and probes that are not co-located
with the BlueFlow application server.

## Summary of findings

### Phase 1 — Research

- **No existing HL7/MLLP analyzer for Zeek.** Confirmed gap across
  packages.zeek.org, GitHub, and academic sources. Custom Spicy grammar is the
  recommended path — MLLP framing is trivial (~15-30 lines of Spicy).
- **Zeek logs map well to BlueFlow Asset fields.** `dns.log` closes the
  hostname gap from #47. `ssl.log` provides manufacturer hints via TLS cert
  metadata. `conn.log` gives richer connection data (duration, byte counts,
  protocol detection) and topology edges.
- **MAC-IP resolution works in live capture.** `conn.log` L2 fields
  (`orig_l2_addr`, `resp_l2_addr`) populate in live-capture mode, matching
  tshark's coverage for both DHCP and static-IP devices. Pcap replay does not
  populate L2 fields — Docker bridge networks provide a viable dev/test
  workaround.
- **Resource footprint fits small hospitals.** Single-threaded Zeek on a
  sub-100 Mbps link needs ~1 core and 1-2 GB RAM. BSD 3-Clause licensed.

### Phase 2 — Prototype

- Custom Spicy MLLP analyzer (`mllp.spicy` + `mllp.evt`) and Zeek logging
  script (`hl7_extract.zeek`) written and tested.
- **124/124 message parity** with the #47 tcpflow/tshark pipeline against the
  sample pcap (`spikes/hl7/data/hl7.pcap`).
- Extracted fields: `sending_app`, `sending_facility`, `receiving_app`,
  `receiving_facility`, `message_timestamp`, `message_type`, `message_id`,
  `hl7_version`, `patient_location`, `equipment_id`.
- `run.sh` provides a reproducible compile-and-run workflow.

## Trade-offs

### Why Zeek over tcpflow/tshark

The #47 spike used tcpflow/tshark as a proof-of-concept for HL7 extraction.
Both are viable tools, but Zeek is a better foundation for a production probe:

| Dimension | tcpflow/tshark | Zeek |
|---|---|---|
| Protocol analysis | Raw flow reconstruction | Structured per-protocol logs |
| DNS hostname resolution | Gap — needs separate tooling | Built-in (`dns.log`) |
| TLS metadata | Not available | `ssl.log` (cert CN/SAN/issuer) |
| Extensibility | Script per protocol | Spicy grammar + Zeek script |
| Multi-probe support | No built-in agent model | Stateless probe with `ActiveHTTP` or sidecar push |
| Operational overhead | Cron + scripts | Daemon (`zeekctl`) — heavier, but structured |

The main cost is operational complexity: Zeek is a persistent daemon that needs
monitoring. For a product that already manages PostgreSQL, Redis, and Celery,
this is incremental.

### Multi-probe constraints

The architecture must not assume Zeek runs on the same host as BlueFlow, or
that there is only one probe per deployment. This rules out file polling and
named pipes as integration strategies (see `integration-architecture.md`).

Key concerns introduced by multi-probe:

1. **Deduplication** — Overlapping probe coverage (e.g. two probes on the same
   span port) can produce duplicate data. Deduplicate by MSH-10 message control
   ID + timestamp for HL7, and by connection tuple + Zeek UID for conn data.
2. **Probe identity** — Each probe needs an API token and must be associated
   with a network/CIDR to disambiguate overlapping RFC1918 address space.
3. **Probe liveness** — Silent probe could mean quiet network or dead probe.
   BlueFlow needs a heartbeat or last-seen tracker per probe.
4. **Configuration distribution** — New analyzers (e.g. DICOM) must reach N
   probes. Initial approach: manual deployment. Future: config pull endpoint.

## Applicability to future work

- **#48 (FHIR):** FHIR runs over HTTP/REST. Zeek already produces `http.log`
  with URIs, methods, status codes, and content types. A Zeek script can detect
  FHIR endpoints (paths matching `/fhir/`, content type `application/fhir+json`)
  without a custom Spicy analyzer. Low incremental effort.
- **#44 (DICOM):** A community Zeek DICOM analyzer exists on packages.zeek.org.
  Needs evaluation for AE Title extraction, but the foundation is there. Zeek
  adoption makes this feasible — tcpflow/tshark would require building DICOM
  parsing from scratch.
- **#49 (Naabu + Zeek):** Naabu is an active scanner; Zeek is passive. They
  complement rather than overlap. Both can push results to BlueFlow via the same
  HTTP integration pattern — a probe-side sidecar or script that POSTs to the
  asset API. Adopting Zeek establishes the push model that Naabu can reuse.
