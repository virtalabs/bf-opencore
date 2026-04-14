# SPIKE: Evaluate HL7 Passive Scanning Integration Strategies

**Issue:** #47
**Date:** 2026-04-14
**Status:** Complete
**Recommendation:** Pursue — passive capture prototype in FY2026, active MLLP endpoint in FY2027

---

## Summary

HL7 v2.x traffic parsing is a viable path for medical device discovery in BlueFlow. The protocol is plaintext, well-structured, and widely deployed across clinical device categories. Both passive (SPAN-based) and active (MLLP endpoint) capture modes are worth building, targeting different deployment scenarios.

### Timeline

| Phase | Fiscal Year | Target | Scope |
|---|---|---|---|
| **Passive prototype** | FY2026 (by Sep 30, 2026) | Working SPAN-based capture with HL7 parsing and asset upsert | Core parsing layer, TCP reassembly via pyshark/tshark, device fingerprinting, topology edges |
| **Active MLLP endpoint** | FY2027 (Oct 2026+) | Dual-mode MLLP listener (plaintext + TLS) | Reuses FY2026 parsing layer, adds MLLP transport, TLS config, ACK/NAK handling |

The passive prototype establishes the shared HL7 parsing and asset-mapping layer, which the active mode will reuse. Building passive first also aligns with BlueFlow's small hospital target market, where SPAN-based deployment is the lowest-friction option.

---

## 1. HL7 Message Types Carrying Device-Identifying Information

### High-Value Message Types

| Message Type | Description | Device Info Quality |
|---|---|---|
| **ORU^R01** (Observation Result) | Vitals, lab results, vent parameters | Best — OBX-18 carries equipment serial/ID |
| **ESU^U01** (Equipment Status Update) | Lab instrument status changes | Excellent — EQU-1 explicitly identifies equipment |
| **EAN^U09** (Equipment Notification) | Reagent/calibration alerts | Excellent — same as ESU |
| **ADT** (A01–A62) | Admit/discharge/transfer | Limited — MSH-3 only |
| **ORM^O01** (Order) | Orders routed to devices | Moderate — ORC-18 (entering device) |

### Key Segments and Fields

| Segment.Field | Data | Reliability |
|---|---|---|
| **MSH-3** (Sending Application) | Application/vendor name (e.g., "PHILIPS_MX800") | Always present — best single field |
| **MSH-4** (Sending Facility) | Department/site code | Always present, not device-specific |
| **MSH-12** (Version ID) | HL7 version (2.3, 2.5, 2.7, etc.) | Always present |
| **OBX-18** (Equipment Instance ID) | Serial number, manufacturer namespace, OID | ~30–50% of deployments |
| **OBX-3** (Observation Identifier) | LOINC/local code — implies device class | Present in all ORU messages |
| **PRT-10** (Participation Device) | Device ID with UDI support | v2.7+ only — minority of deployments |
| **PRT-16** (Device Type) | SNOMED/GMDN coded device type | v2.7+ only, rarely populated |
| **PRT-17** (Device Manufacturer) | Explicit manufacturer name | v2.7+ only |
| **EQU-1** (Equipment Instance ID) | Serial number, namespace, universal ID | Present in ESU/EAN messages |
| **PV1-3** (Patient Location) | Bed/room/unit — maps device to location | Usually present in ADT/ORU |

### What Can Be Extracted Passively vs. What Cannot

**Reliably extractable:**
- Source/destination IP (network layer — device anchor)
- Sending application name (MSH-3)
- Device class inference via observation codes (OBX-3)
- Activity patterns and message volume (monitor vs. lab analyzer vs. pump)
- Patient location / device-to-location mapping (PV1-3)

**Sometimes extractable (depends on deployment):**
- Equipment serial number (OBX-18, EQU-1)
- Manufacturer (PRT-17 or inferred from MSH-3)
- Device type code (PRT-16)

**Not available from HL7 traffic — requires other methods:**
- Model number, firmware/software version
- MAC address (requires L2 capture or ARP)
- Hostname/FQDN (requires DNS reverse lookup)
- OS fingerprint (requires TCP fingerprinting, e.g., p0f)
- Full asset inventory attributes (purchase date, warranty, etc.)

---

## 2. Devices That Communicate via HL7 v2.x

### Primary HL7 v2.x Speakers (Direct or via Gateway)

| Device Category | Examples | Message Types | Notes |
|---|---|---|---|
| Patient monitors | Philips IntelliVue, GE CARESCAPE, Draeger Infinity | ORU^R01 | Highest-volume source; some use IEEE 11073→HL7 gateway |
| Lab analyzers | Roche cobas, Siemens Atellica, Abbott Alinity | ORU^R01, ESU^U01 | Most mature HL7 v2.x ecosystem |
| POCT devices | Abbott i-STAT, Siemens RAPIDPoint | ORU^R01 | Via POCT data manager, not directly |
| Infusion pumps | BD Alaris, Baxter Spectrum, ICU Medical Plum 360 | ORU^R01, RAS | Via pump gateway/server (e.g., BD Alaris Gateway) |
| Ventilators | Draeger Evita, Hamilton C6, Medtronic PB840 | ORU^R01 | Via device integration engine (Capsule, Bernoulli) |
| Pharmacy automation | BD Pyxis, Omnicell | RDE, RDS, DFT | Automated dispensing cabinets |
| ECG systems | GE MUSE, Philips TraceMasterVue | ORU^R01 | Interpretive results; waveforms may be proprietary |
| Blood bank | Ortho Vision, Bio-Rad IH-1000 | ORU^R01, ORM^O01 | Tightly integrated with LIS |

### Not Visible on HL7 v2.x

- **Imaging modalities** (CT, MRI, ultrasound) — use DICOM; the RIS speaks HL7, not the scanner
- **Modern wearables/IoT** — use FHIR, Bluetooth, or cloud APIs
- **Smart beds, environmental sensors** — proprietary protocols or MQTT/BACnet

---

## 3. Parser Evaluation

### Recommendation: python-hl7

| Criterion | python-hl7 (`hl7`) | hl7apy | Manual parsing |
|---|---|---|---|
| Parse HL7 v2.x | Yes | Yes | Yes |
| Schema validation | No | Yes (v2.1–v2.9) | No |
| MLLP support | Built-in (client + asyncio server) | No | No |
| Field extraction | Terser paths (`msg['OBX.18']`) | OOP + Terser | String splitting |
| Performance | Fast (string splitting) | Moderate (object graph) | Fastest |
| License | BSD | MIT | N/A |
| Maintenance | Stable, low activity (~260 stars) | Stable, low activity (~175 stars) | Self-maintained |

**python-hl7** is the right choice for BlueFlow's use case:
- We need to **extract** fields, not validate or generate messages
- Built-in MLLP server support means we can stand up a listener with minimal code
- BSD license is compatible
- Lightweight enough for streaming/high-throughput parsing

**hl7apy** is the fallback if we later need schema-aware validation or message generation. It can be paired with python-hl7's MLLP module.

---

## 4. Transport: MLLP and Capture Strategy

### MLLP (Minimum Lower Layer Protocol)

HL7 v2.x messages are transported over TCP using MLLP framing:
```
<0x0B> + HL7_MESSAGE + <0x1C><0x0D>
```

Standard MLLP is **plaintext TCP**. Secure MLLP (MLLP+TLS) is increasingly deployed.

### Passive Capture vs. Active Endpoint

#### Detailed Comparison

| Criterion | Passive Capture (SPAN/Tap) | Active MLLP Endpoint |
|---|---|---|
| **Setup complexity** | Low — network admin mirrors a switch port, BlueFlow connects | Medium-high — integration engine admin creates outbound channels per source |
| **Who does the work** | Network admin (familiar with SPAN) | Interface engine admin (specialized, may be a contractor or managed service) |
| **Change control burden** | Low — network infrastructure only | Higher — touches clinical integration layer, often requires change advisory board approval |
| **Time to deploy** | Hours | Days to weeks (change control lead time) |
| **Ongoing maintenance** | Minimal — SPAN port is set-and-forget | Channel monitoring, cert rotation, interface engine upgrades can break channels |
| **Coverage breadth** | Broad — sees all HL7 traffic on the mirrored segment | Selective — only sees traffic from explicitly configured channels |
| **TLS environments** | Blind — encrypted traffic is opaque | Works — receives decrypted messages as a legitimate endpoint |
| **TCP reassembly** | Required — must reassemble streams from raw packets (pyshark/tshark) | Not needed — messages arrive fully framed via MLLP |
| **Data reliability** | Best-effort — dropped packets, retransmissions, no ACK | Reliable — ACK/NAK flow control, guaranteed delivery |
| **Topology accuracy** | Sees actual network paths (L3/L4) | Sees logical paths through the interface engine |
| **PHI exposure** | Higher — captures full raw traffic including non-HL7 | Scoped — only receives HL7 messages from configured channels |
| **Clinical system impact** | None — purely observational | Low but nonzero — BlueFlow becomes a destination in the message flow |
| **Failure mode ownership** | BlueFlow team owns the capture appliance | Hospital team owns channel availability in their interface engine |
| **Small hospital fit** | Strong — minimal staff required, familiar workflow | Weaker — requires integration expertise that small hospitals may lack |

#### Recommendation: Support Both, Default to Passive

BlueFlow targets small hospitals where ease of deployment is a competitive advantage. SPAN-based passive capture should be the **primary deployment mode** — it requires no changes to clinical systems, no coordination with interface engine administrators, and no change control process.

Active MLLP endpoint should be supported as an **alternative for sites that need it** — specifically hospitals that have adopted TLS on their HL7 channels, or that prefer a structured integration approach.

The HL7 parsing layer is identical regardless of capture mode. The only difference is how messages arrive:

| Mode | Message Delivery |
|---|---|
| Passive | tcpflow (external) → BlueFlow reads reassembled streams → strip MLLP framing → parse HL7 → Celery task → Asset upsert |
| Active | MLLP socket → strip framing → parse HL7 → Celery task → Asset upsert |
| Active + TLS | TLS socket → MLLP → strip framing → parse HL7 → Celery task → Asset upsert |

#### Integration Architecture

Passive capture follows BlueFlow's existing pattern for external tool integration (same as nmap/portscan, ping, fingerprint):

- **External tool does the heavy lifting** — tcpflow handles packet capture and TCP stream reassembly. BlueFlow scans the reassembled output for MLLP framing and extracts HL7 messages.
- **BlueFlow wraps the tool** — calls tcpflow via the `sh` library (consistent with existing nmap/ping wrappers), reads reassembled stream files, and parses HL7 content.
- **Results flow through Celery** — a task receives parsed HL7 messages, extracts device fingerprints (MSH-3, OBX-18, OBX-3, source/dest IP), and upserts into the Asset model.
- **Provenance via Scan model** — each capture session creates a Scan record with tcpflow command provenance, matching the existing pattern for nmap scans.

tcpflow is a **runtime dependency** on the host (like nmap is today), not a Python library bundled with BlueFlow.

#### Why tcpflow Over tshark

| Criterion | tcpflow | tshark |
|---|---|---|
| **Purpose** | TCP stream reassembly (does one thing well) | Full protocol analyzer (massive feature set) |
| **macOS** | `brew install tcpflow` (standalone) | Requires full Wireshark install |
| **Linux** | `apt install tcpflow` (standalone) | `apt install tshark` (standalone) |
| **Output** | One file per TCP stream — raw bytes, easy to scan for MLLP framing | Structured protocol dissection (JSON, field extraction) |
| **Weight** | Lightweight (~1 MB) | Heavy (~50+ MB with dependencies) |
| **License** | GPLv3 (external binary, not bundled) | GPLv2 (external binary, not bundled) |

tcpflow is the right fit for the FY2026 prototype — it reconstructs TCP streams and writes them to files, which BlueFlow scans for `0x0B...0x1C0x0D` MLLP frames. No protocol dissection engine needed.

**tshark as a fallback:** If we later need deeper protocol analysis (e.g., HL7 field-level filtering at the capture layer, or handling edge cases in malformed TCP streams), tshark can be swapped in. The parsing layer above the capture tool does not change.

#### Small Hospital Deployment Context

- **Passive is the easier sell** — "plug into a SPAN port and go" vs. "configure your interface engine to send us a copy of all HL7 traffic"
- **Plaintext MLLP is still common** — smaller facilities run older interface engines (Mirth Connect 3.x, legacy Cloverleaf) with less security staff driving TLS adoption
- **Active mode is future-proofing** — as TLS adoption grows, sites can migrate from passive to active without changing anything in BlueFlow's parsing layer
- **Supporting both modes from day one is low-cost** — the parsing and asset-mapping code is shared; only the transport layer differs

---

## 5. Cross-Reference: Target Device Coverage

Compared against the candidate device lists from spikes #55 (medical) and #56 (network infrastructure):

- **Medical devices with HL7 v2.x visibility:** Patient monitors, lab analyzers, infusion pumps (via gateway), ventilators (via integration engine), POCT devices, pharmacy automation, blood bank systems, ECG systems
- **Medical devices NOT visible via HL7:** Imaging modalities (need DICOM — see spike #48 for FHIR), wearables, smart beds
- **Network infrastructure:** Not applicable — switches, routers, firewalls do not speak HL7

HL7 v2.x covers the **clinical device** segment well but provides no coverage for imaging or network infrastructure.

---

## 6. Topology Mapping Opportunity

Every HL7 message contains both a sender and receiver, making HL7 traffic a natural source for building a clinical network topology map.

### Data Available Per Message

| Field | Topology Role |
|---|---|
| **Source IP** (network layer) | Sending device/gateway address |
| **Destination IP** (network layer) | Receiving system address |
| **MSH-3** (Sending Application) | Sending device/application identity |
| **MSH-5** (Receiving Application) | Receiving system identity |
| **MSH-4 / MSH-6** (Sending/Receiving Facility) | Department or site grouping |
| **MSH-7** (Message Timestamp) | Edge timestamp — when communication occurred |
| **MSH-9** (Message Type) | Edge label — what kind of data is flowing (results, orders, status) |

### What This Enables

- **Communication graph** — directed edges from sender → receiver, weighted by message volume, building a map of which devices talk to which systems over time
- **Integration hub identification** — interface engines (Mirth, Rhapsody) appear as high-degree nodes; these are critical infrastructure and high-value targets for security analysis
- **Anomaly detection** — a device communicating with an unexpected destination (outside its normal pattern) is a potential indicator of compromise or misconfiguration
- **Segmentation gap analysis** — HL7 traffic crossing VLAN boundaries reveals network segmentation weaknesses (e.g., clinical devices reaching admin-network systems directly)
- **Device activity tracking** — devices that stop sending messages may be offline, decommissioned, or compromised; message timing patterns distinguish always-on devices (monitors) from intermittent ones (lab analyzers)

### Implementation Notes

No additional parsing is required beyond what is already planned for device discovery. The sender/receiver relationship (MSH-3 + source IP → MSH-5 + destination IP) comes from the same message header. The topology map is a second view of the same data, stored as edges rather than nodes.

The active MLLP endpoint approach is advantageous here — the interface engine forwards messages from all connected devices, giving BlueFlow visibility into the full routing path rather than just traffic on a single network segment.

---

## 7. Decision

**Pursue** — HL7 v2.x integration is viable and covers a significant portion of the clinical device landscape. Passive capture prototype in FY2026, active MLLP endpoint in FY2027.

### FY2026 — Passive Capture Prototype (by Sep 30, 2026)

1. Add `python-hl7` as a dependency; document tcpflow as a runtime dependency (like nmap)
2. Build tcpflow wrapper in `blueflow/hl7/` — call tcpflow via `sh` to capture on a SPAN interface and reassemble TCP streams into per-connection files
3. Build MLLP frame extractor — scan tcpflow output files for `0x0B...0x1C0x0D` boundaries to extract individual HL7 messages
4. Build the shared HL7 parsing layer — extract device fingerprints (IP + MSH-3 + OBX-18 + OBX-3) using `python-hl7`
5. Build Celery task to receive parsed messages, map HL7 fields to Asset model fields (MSH-3 → asset name/vendor, OBX-3 → device class, OBX-18 → serial number), and upsert into the Asset model
6. Create Scan records with tcpflow command provenance (consistent with existing nmap/portscan pattern)
7. Store sender→receiver edges (MSH-3/IP → MSH-5/IP + timestamp + message type) for topology mapping

### FY2027 — Active MLLP Endpoint (Oct 2026+)

1. Build dual-mode MLLP listener (plaintext + TLS) reusing the FY2026 parsing layer and Celery tasks
2. Add ACK/NAK response handling for reliable message delivery
3. Make TLS configurable (cert/key paths, optional client cert verification)
4. Provide deployment documentation for interface engine configuration (Mirth Connect, Rhapsody)

### Open Questions

- What is the PHI handling strategy? HL7 messages contain patient data (PID segment) that BlueFlow does not need and should not store.
- How do we handle the many-to-one problem where a device integration engine (e.g., Capsule) aggregates multiple devices behind a single MSH-3/IP? OBX-18 disambiguation may be needed.
- tcpflow writes stream files to disk — what is the cleanup strategy for processed files? Disk usage in long-running capture sessions needs consideration.
