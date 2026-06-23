"""
Static registries for topology inference.

PORT_SERVICE_MAP
    port (int) → (service_name: str, protocol: Protocol)
    Covers IT, OT, and medical protocol ports.

DEVICE_CLASS_INITIATES
    device_class (str) → frozenset of service names the class initiates outbound.

    Semantics: if device A's class initiates service S, and device B exposes
    a port that maps to service S, then there is a directed edge A → B on S.
    The wildcard "*" means the class initiates any service (routers, firewalls).
"""

from __future__ import annotations

PORT_SERVICE_MAP: dict[int, tuple[str, str]] = {
    # ── IT services ────────────────────────────────────────────
    21:    ("ftp",     "tcp"),
    22:    ("ssh",     "tcp"),
    23:    ("telnet",  "tcp"),
    25:    ("smtp",    "tcp"),
    53:    ("dns",     "udp"),
    80:    ("http",    "tcp"),
    443:   ("https",   "tcp"),
    445:   ("smb",     "tcp"),
    3306:  ("mysql",   "tcp"),
    3389:  ("rdp",     "tcp"),
    5900:  ("vnc",     "tcp"),
    8080:  ("http",    "tcp"),
    8443:  ("https",   "tcp"),

    # ── Medical / clinical protocols ───────────────────────────
    104:   ("dicom",        "tcp"),   # DICOM primary
    2761:  ("dicom",        "tcp"),   # DICOM TLS
    2762:  ("dicom",        "tcp"),   # DICOM TLS alt
    11112: ("dicom",        "tcp"),   # DICOM alt
    2575:  ("hl7",          "tcp"),   # HL7 MLLP
    4006:  ("hl7",          "tcp"),   # HL7 alt
    3702:  ("ws_discovery", "udp"),   # WS-Discovery (device broadcast)

    # ── OT / ICS protocols ─────────────────────────────────────
    102:   ("s7comm",  "tcp"),   # Siemens S7
    502:   ("modbus",  "tcp"),   # Modbus/TCP
    4840:  ("opcua",   "tcp"),   # OPC-UA
    20000: ("dnp3",    "tcp"),   # DNP3
    44818: ("enip",    "tcp"),   # EtherNet/IP
    2404:  ("iec104",  "tcp"),   # IEC 60870-5-104
    1962:  ("pcworx",  "tcp"),   # Phoenix Contact
    9600:  ("omron",   "tcp"),   # OMRON FINS
    1911:  ("niagara", "tcp"),   # Niagara Fox
    47808: ("bacnet",  "udp"),   # BACnet
    5007:  ("melsec",  "tcp"),   # Mitsubishi MELSEC
    135:   ("dcom",    "tcp"),   # DCOM/RPC
}


DEVICE_CLASS_INITIATES: dict[str, frozenset[str]] = {
    # ── Medical imaging / monitoring ───────────────────────────
    # patient_monitor (e.g. IntelliVue MX700): sends vital-sign/alarm data via
    # HL7 MLLP to a clinical workstation or integration engine.  Does not
    # initiate DICOM associations or web sessions.
    "patient_monitor":        frozenset({"hl7"}),
    # imaging_system (e.g. Affiniti US): sends completed studies to PACS and
    # workstations via DICOM C-STORE.  Does not initiate HTTP/HTTPS.
    "imaging_system":         frozenset({"dicom"}),
    "infusion_pump":          frozenset({"hl7", "http", "https"}),
    "ventilator":             frozenset({"hl7", "http", "https"}),
    "clinical_workstation":   frozenset({"dicom", "hl7", "https", "http", "ssh", "rdp", "smb", "ftp"}),
    "pacs_server":            frozenset({"dicom", "https", "ssh"}),
    "ehr_server":             frozenset({"hl7", "http", "https", "ssh", "smb", "mysql"}),
    "medical_device_server":  frozenset({"hl7", "dicom", "http", "https", "ssh"}),

    # ── Networking ─────────────────────────────────────────────
    "router":                 frozenset({"*"}),
    "switch":                 frozenset({"*"}),
    "firewall":               frozenset({"*"}),
    "gateway":                frozenset({"*"}),
    "vpn_concentrator":       frozenset({"*"}),

    # ── OT / ICS ───────────────────────────────────────────────
    "plc":                    frozenset({"modbus", "s7comm", "enip", "opcua", "dnp3"}),
    "hmi":                    frozenset({"modbus", "s7comm", "enip", "opcua", "dnp3",
                                         "http", "https", "rdp", "vnc"}),
    "engineering_workstation": frozenset({"modbus", "s7comm", "enip", "opcua", "dnp3",
                                          "http", "https", "ssh", "rdp"}),
    "historian":              frozenset({"opcua", "http", "https", "ssh", "smb"}),
    "scada_server":           frozenset({"modbus", "s7comm", "enip", "opcua", "dnp3",
                                         "http", "https", "ssh"}),
    "rtu":                    frozenset({"modbus", "dnp3", "iec104"}),

    # ── Generic ────────────────────────────────────────────────
    "workstation":            frozenset({"http", "https", "ssh", "rdp", "smb", "ftp"}),
    "server":                 frozenset({"http", "https", "ssh", "smb", "mysql", "ftp"}),
    "unknown":                frozenset({"http", "https"}),
}


def resolve_port(port: int) -> tuple[str, str] | None:
    """Return (service_name, protocol) for a known port, or None."""
    return PORT_SERVICE_MAP.get(port)


def get_initiated_services(device_class: str) -> frozenset[str]:
    """Return the set of service names a device class initiates outbound."""
    dc = device_class.lower().replace("-", "_").replace(" ", "_")
    if dc in DEVICE_CLASS_INITIATES:
        return DEVICE_CLASS_INITIATES[dc]
    for key in DEVICE_CLASS_INITIATES:
        if dc.startswith(key) or key in dc:
            return DEVICE_CLASS_INITIATES[key]
    return DEVICE_CLASS_INITIATES["unknown"]
