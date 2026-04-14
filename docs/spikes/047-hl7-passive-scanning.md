# SPIKE: Evaluate HL7 Passive Scanning Integration Strategies

**Issue:** #47
**Date:** 2026-04-14
**Status:** Complete
**Recommendation:** Pursue — with active MLLP endpoint approach, not passive tap

---

## Summary

HL7 v2.x passive traffic parsing is a viable path for medical device discovery in BlueFlow. The protocol is plaintext, well-structured, and widely deployed across clinical device categories. However, the practical approach should be an **active MLLP listener** (receiving a copy of messages) rather than raw passive network capture, due to increasing TLS adoption and TCP reassembly complexity.

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

### Passive Tap vs. Active Endpoint

| Approach | Pros | Cons |
|---|---|---|
| **Passive capture** (SPAN/tap) | Zero config on clinical systems; discover without participating | Blind to TLS; TCP reassembly is complex; no ACK; HIPAA surface area |
| **Active MLLP endpoint** | Reliable; works with TLS; standard integration pattern; ACK/NAK flow | Requires interface engine config; you become part of the message flow |

### Recommendation: Active MLLP Endpoint (Supporting Both Transport Modes)

Passive capture is attractive for zero-touch discovery but is increasingly impractical as hospitals adopt TLS. The recommended approach:

1. **Deploy BlueFlow as an MLLP listener** that receives a copy of HL7 traffic (most interface engines — Mirth Connect, Rhapsody, Epic Bridges — support routing a copy of messages to additional destinations)
2. **Support both plaintext MLLP and MLLP+TLS** on the listener — these are the same protocol with an optional TLS wrapper, not incompatible formats
3. **Parse MSH-3 + source IP** from every message for baseline device inventory
4. **Extract OBX-18, OBX-3, PRT, and EQU** fields when present for enriched device metadata
5. **Correlate with existing BlueFlow asset records** by IP address to augment the asset model

This avoids TCP reassembly complexity and fits into existing clinical integration patterns.

#### Target deployment: Small hospital AMPs

BlueFlow targets small hospitals for asset management and security analysis. In this segment:

- **Plaintext MLLP is still common** — smaller facilities run older interface engines (Mirth Connect 3.x, legacy Cloverleaf) with less security staff driving TLS adoption
- **TLS adoption is growing** — even small hospitals are tightening internal network security under HIPAA pressure
- **Supporting both modes from day one is low-cost** — the difference is `ssl.wrap_socket()` on the TCP connection; the HL7 parsing layer is identical regardless of transport security
- **Dual-mode support is a buyer checkbox** — security-conscious evaluators expect TLS support even if their current environment doesn't use it

---

## 5. Cross-Reference: Target Device Coverage

Compared against the candidate device lists from spikes #55 (medical) and #56 (network infrastructure):

- **Medical devices with HL7 v2.x visibility:** Patient monitors, lab analyzers, infusion pumps (via gateway), ventilators (via integration engine), POCT devices, pharmacy automation, blood bank systems, ECG systems
- **Medical devices NOT visible via HL7:** Imaging modalities (need DICOM — see spike #48 for FHIR), wearables, smart beds
- **Network infrastructure:** Not applicable — switches, routers, firewalls do not speak HL7

HL7 v2.x covers the **clinical device** segment well but provides no coverage for imaging or network infrastructure.

---

## 6. Decision

**Pursue** — HL7 v2.x integration via an active MLLP listener is viable and covers a significant portion of the clinical device landscape.

### Suggested Next Steps

1. Add `python-hl7` as a dependency
2. Build a dual-mode MLLP listener service (plaintext + TLS) — Celery worker, Django management command, or standalone asyncio process
3. Implement a parser that extracts device fingerprints (IP + MSH-3 + OBX-18 + OBX-3) and upserts into BlueFlow's Asset model
4. Define mapping rules from HL7 fields to Asset model fields (MSH-3 → asset name/vendor, OBX-3 → device class, OBX-18 → serial number)
5. Make TLS configurable (cert/key paths, optional client cert verification) for sites that require it

### Open Questions

- Should the MLLP listener run as a Celery worker, a Django management command, or a standalone service?
- What is the PHI handling strategy? HL7 messages contain patient data (PID segment) that BlueFlow does not need and should not store.
- How do we handle the many-to-one problem where a device integration engine (e.g., Capsule) aggregates multiple devices behind a single MSH-3/IP? OBX-18 disambiguation may be needed.
