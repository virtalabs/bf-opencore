#!/usr/bin/env python3
"""
dicom_asset_poc.py — DICOM asset discovery from PCAP via nfstream.

Extracts per-endpoint asset records (IP, MAC, AE title, modality, SOP classes)
from DICOM TCP flows (ports 104 and 2104) using byte-level PDU parsing per
PS3.8 Table 9-11. Falls back to data-rate profiling for pre-capture sessions.
"""

import argparse
import json
import re
import sys

from nfstream import NFPlugin, NFStreamer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DICOM_PORTS = {104, 2104}

# PS3.6 SOP class UID → modality abbreviation (5.1.* sub-arc only)
SOP_TO_MODALITY = {
    "1.2.840.10008.5.1.4.1.1.2":   "CT",   # CT Image Storage
    "1.2.840.10008.5.1.4.1.1.4":   "MR",   # MR Image Storage
    "1.2.840.10008.5.1.4.1.1.6.1": "US",   # Ultrasound Image Storage
    "1.2.840.10008.5.1.4.1.1.7":   "SC",   # Secondary Capture
    "1.2.840.10008.5.1.4.1.1.1":   "CR",   # Computed Radiography
    "1.2.840.10008.5.1.4.1.1.1.1": "DX",   # Digital X-Ray
    "1.2.840.10008.5.1.4.31":      "MWL",  # Modality Worklist
}

# Modality priority when multiple SOP classes are present (higher index = preferred)
MODALITY_PRIORITY = ["MWL", "SC", "CR", "DX", "US", "MR", "CT"]

# SOP class UID regex — restricted to 5.1.* to exclude transfer syntaxes
SOP_PATTERN = re.compile(rb"1\.2\.840\.10008\.5\.1\.[0-9.]+")

# Philips Healthcare private OID arcs (two separate prefixes)
PHILIPS_UID_PREFIXES = [b"1.2.840.113704.", b"1.3.46."]

# Static OUI vendor table (first 3 MAC octets, uppercase no colons)
OUI_VENDOR = {
    "989096": "Dell",
    "00A0C9": "Intel",
    "001B21": "Intel",
    "001517": "Philips Medical",
    "0060B0": "Philips",
    "D45D64": "Philips",
    "0050C2": "Capsule Tech",
    "001B17": "Palo Alto",
    "005056": "VMware",
    "000C29": "VMware",
    "001C14": "VMware",
    "EC8631": "Siemens Healthineers",
    "3CE1A1": "GE Healthcare",
    "0003FF": "Microsoft",
    "BC9FEF": "Apple",
    "E8F724": "Arista Networks",  # gateway MAC seen in this capture
}

# Gateway MAC observed in the RX-only SPAN capture (dst_mac for all SCP flows)
SPAN_GATEWAY_MAC = "e8:f7:24:6b:4e:01"


# ---------------------------------------------------------------------------
# Helpers — payload extraction and DICOM PDU parsing
# ---------------------------------------------------------------------------

def get_tcp_payload(ip_packet: bytes) -> bytes:
    """Return TCP payload bytes from a raw IP packet (IP header start).

    Accounts for variable IP and TCP header lengths (TCP options).
    Returns b"" on any parse error or non-TCP packet.
    """
    if len(ip_packet) < 20:
        return b""
    ihl = (ip_packet[0] & 0x0F) * 4
    if ihl < 20 or len(ip_packet) < ihl + 13:
        return b""
    if ip_packet[9] != 6:  # not TCP
        return b""
    tcp_hlen = ((ip_packet[ihl + 12] >> 4) & 0x0F) * 4
    if tcp_hlen < 20:
        return b""
    payload_start = ihl + tcp_hlen
    if payload_start >= len(ip_packet):
        return b""
    return ip_packet[payload_start:]


def parse_assoc_rq(pdu: bytes) -> dict | None:
    """Parse Called/Calling AE titles from an A-ASSOCIATE-RQ PDU (PS3.8 Table 9-11).

    Returns {"called": str, "calling": str} or None if PDU is invalid/too short.
    Validates protocol-version and reserved fields to reject mid-stream false positives.
    """
    if len(pdu) < 74 or pdu[0] != 0x01:
        return None
    if pdu[1] != 0x00:          # reserved byte must be zero
        return None
    pdu_len = int.from_bytes(pdu[2:6], "big")
    if pdu_len < 60 or pdu_len > 0xFFFF:  # sanity check PDU length
        return None
    if pdu[6:8] != b"\x00\x01":  # protocol version must be 1
        return None
    if pdu[8:10] != b"\x00\x00":  # reserved bytes must be zero
        return None
    called  = pdu[10:26].decode("ascii", errors="replace").strip()
    calling = pdu[26:42].decode("ascii", errors="replace").strip()
    # Reject non-printable results (indicates mid-stream false positive)
    printable = set(" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~")
    if called  and not all(c in printable for c in called):
        return None
    if calling and not all(c in printable for c in calling):
        return None
    if not called and not calling:
        return None
    return {"called": called, "calling": calling}


def extract_sop_classes(pdu: bytes) -> list:
    """Extract unique SOP class UIDs from raw PDU bytes via regex.

    Restricted to 1.2.840.10008.5.1.* to avoid matching transfer syntax
    UIDs (1.2.840.10008.1.*) or application context UIDs (1.2.840.10008.3.*).
    """
    seen = set()
    result = []
    for m in SOP_PATTERN.findall(pdu):
        uid = m.decode("ascii").rstrip(".")
        if uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


def has_philips_uid(pdu: bytes) -> bool:
    """Return True if any Philips private OID arc prefix appears in pdu bytes."""
    return any(prefix in pdu for prefix in PHILIPS_UID_PREFIXES)


# AE title prefix → primary modality (used to disambiguate multi-SOP A-ASSOCIATE-RQ)
AE_PREFIX_MODALITY = {
    "US": "US", "CT": "CT", "MR": "MR", "PT": "PT",
    "DX": "DX", "CR": "CR", "XA": "XA", "NM": "NM",
    "RF": "RF", "MG": "MG", "IO": "IO", "OT": "OT",
}


def resolve_modality(sop_classes: list, ae_title: str = "") -> str:
    """Return the most specific modality from SOP UIDs, with AE title prefix as tiebreaker.

    Many A-ASSOCIATE-RQ PDUs list multiple storage SOP classes. When the AE title
    encodes the primary modality (US1033619 → US), use it to select the best match
    rather than always taking the highest-priority SOP class.
    """
    found = {}
    for uid in sop_classes:
        m = SOP_TO_MODALITY.get(uid)
        if m:
            found[m] = uid

    if not found:
        return ""

    # If AE title prefix unambiguously names one of the found modalities, prefer it
    ae_prefix = ae_title[:2].upper() if ae_title else ""
    if ae_prefix in AE_PREFIX_MODALITY and AE_PREFIX_MODALITY[ae_prefix] in found:
        return AE_PREFIX_MODALITY[ae_prefix]

    return max(found.keys(), key=lambda m: MODALITY_PRIORITY.index(m) if m in MODALITY_PRIORITY else -1)


def infer_modality_from_rate(mbps: float) -> str:
    """Classify modality from sustained data rate (fallback for pre-capture flows)."""
    if mbps > 2.0:
        return "CT/MR"
    if mbps > 0.1:
        return "DR/CR"
    if mbps > 0.01:
        return "US/SC"
    return "MWL"


def mac_to_oui_vendor(mac: str) -> str:
    """Return OUI vendor name from a colon-separated MAC address string."""
    oui = mac.replace(":", "").upper()[:6]
    return OUI_VENDOR.get(oui, "")


def rate_mbps(total_bytes: int, duration_ms: int) -> float:
    """Compute megabits-per-second from byte count and duration in milliseconds."""
    if duration_ms < 1:
        return 0.0
    return round(total_bytes * 8 / duration_ms / 1e3, 3)


# ---------------------------------------------------------------------------
# NFPlugin — per-packet DICOM state accumulation
# ---------------------------------------------------------------------------

class DicomPlugin(NFPlugin):
    """Accumulates DICOM AE titles, SOP classes, and Philips vendor flags per flow."""

    def _process_packet(self, packet, flow):
        try:
            raw = bytes(packet.ip_packet)
        except Exception:
            return
        pdu = get_tcp_payload(raw)
        if not pdu:
            return
        pdu_type = pdu[0]

        if pdu_type == 0x01 and not flow.udps.assoc_parsed:
            result = parse_assoc_rq(pdu)
            if result:
                flow.udps.ae_called   = result["called"]
                flow.udps.ae_calling  = result["calling"]
                flow.udps.sop_classes = extract_sop_classes(pdu)
                flow.udps.assoc_parsed = True

        elif pdu_type == 0x04:
            if has_philips_uid(pdu):
                flow.udps.philips_uid = True
            if not flow.udps.assoc_parsed:
                # pre-capture flow: accumulate any visible SOP UIDs
                for uid in extract_sop_classes(pdu):
                    if uid not in flow.udps.sop_classes:
                        flow.udps.sop_classes.append(uid)

    def on_init(self, packet, flow):
        flow.udps.ae_called    = ""
        flow.udps.ae_calling   = ""
        flow.udps.sop_classes  = []
        flow.udps.philips_uid  = False
        flow.udps.assoc_parsed = False
        self._process_packet(packet, flow)

    def on_update(self, packet, flow):
        self._process_packet(packet, flow)


# ---------------------------------------------------------------------------
# Asset database
# ---------------------------------------------------------------------------

def merge_asset(db: dict, ip: str, mac: str, role: str, ae_title: str,
                sop_classes: list, philips: bool,
                total_bytes: int, duration_ms: int) -> None:
    """Upsert an asset record keyed by IP, merging fields across flows."""
    mbps = rate_mbps(total_bytes, duration_ms)
    mac_note = "rx-only-span-gateway-mac" if mac == SPAN_GATEWAY_MAC else ""

    if ip not in db:
        db[ip] = {
            "ip":                   ip,
            "mac":                  mac,
            "oui_vendor":           mac_to_oui_vendor(mac),
            "ae_title":             ae_title,
            "role":                 role,
            "sop_classes":          list(sop_classes),
            "modality":             resolve_modality(sop_classes, ae_title),
            "inferred_modality":    infer_modality_from_rate(mbps),
            "philips_uid_detected": philips,
            "bytes_sent":           total_bytes,
            "data_rate_mbps":       mbps,
            "mac_note":             mac_note,
            "_total_duration_ms":   duration_ms,
        }
        return

    rec = db[ip]
    if not rec["ae_title"] and ae_title:
        rec["ae_title"] = ae_title
    # union SOP classes
    existing = set(rec["sop_classes"])
    for uid in sop_classes:
        if uid not in existing:
            rec["sop_classes"].append(uid)
            existing.add(uid)
    rec["modality"] = resolve_modality(rec["sop_classes"], rec["ae_title"])
    rec["philips_uid_detected"] |= philips
    if role == "SCU":
        rec["role"] = "SCU"
    rec["bytes_sent"]         += total_bytes
    rec["_total_duration_ms"] += duration_ms
    rec["data_rate_mbps"]      = rate_mbps(rec["bytes_sent"], rec["_total_duration_ms"])
    rec["inferred_modality"]   = infer_modality_from_rate(rec["data_rate_mbps"])


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _plain_table(records: list) -> None:
    headers = ["IP", "MAC", "Vendor", "AE Title", "Role",
               "Modality", "Inferred", "Philips", "Bytes", "Rate(Mbps)", "SOP UIDs"]
    widths = [16, 19, 14, 14, 5, 9, 9, 7, 12, 10, 40]

    header = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header)
    print("-" * len(header))
    for r in records:
        row = [
            str(r.get("ip", "")),
            str(r.get("mac", "")),
            str(r.get("oui_vendor", "")),
            str(r.get("ae_title", "")),
            str(r.get("role", "")),
            str(r.get("modality", "")),
            str(r.get("inferred_modality", "")),
            "Yes" if r.get("philips_uid_detected") else "No",
            str(r.get("bytes_sent", 0)),
            str(r.get("data_rate_mbps", 0.0)),
            " | ".join(r.get("sop_classes", [])),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def print_table(asset_db: dict) -> None:
    records = sorted(asset_db.values(), key=lambda r: r["ip"])
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="DICOM Asset Inventory", show_lines=True)
        for col in ("IP", "MAC", "Vendor", "AE Title", "Role",
                    "Modality", "Inferred", "Philips", "Bytes", "Rate (Mbps)", "SOP UIDs"):
            table.add_column(col, no_wrap=True)
        for r in records:
            table.add_row(
                r["ip"],
                r["mac"],
                r["oui_vendor"],
                r["ae_title"],
                r["role"],
                r["modality"],
                r["inferred_modality"],
                "[green]Yes[/]" if r["philips_uid_detected"] else "No",
                f"{r['bytes_sent']:,}",
                str(r["data_rate_mbps"]),
                "\n".join(r["sop_classes"]),
            )
        Console().print(table)
    except ImportError:
        _plain_table(records)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(pcap_path: str, ports: set, output_json: str | None) -> None:
    asset_db: dict = {}

    print(f"[*] Processing {pcap_path} ...", file=sys.stderr)
    streamer = NFStreamer(
        source=pcap_path,
        decode_tunnels=True,
        udps=DicomPlugin(),
        statistical_analysis=False,
        splt_analysis=0,
    )

    flow_count = dicom_count = 0
    for flow in streamer:
        flow_count += 1
        if flow.protocol != 6:
            continue
        if flow.src_port not in ports and flow.dst_port not in ports:
            continue
        dicom_count += 1

        scu_ip  = flow.src_ip
        scu_mac = flow.src_mac
        scp_ip  = flow.dst_ip
        scp_mac = flow.dst_mac

        merge_asset(
            asset_db, scu_ip, scu_mac, role="SCU",
            ae_title=flow.udps.ae_calling,
            sop_classes=flow.udps.sop_classes,
            philips=flow.udps.philips_uid,
            total_bytes=flow.src2dst_bytes,
            duration_ms=flow.bidirectional_duration_ms,
        )
        merge_asset(
            asset_db, scp_ip, scp_mac, role="SCP",
            ae_title=flow.udps.ae_called,
            sop_classes=[],
            philips=False,
            total_bytes=flow.dst2src_bytes,
            duration_ms=flow.bidirectional_duration_ms,
        )

    print(f"[*] Flows processed: {flow_count:,}  |  DICOM flows: {dicom_count}", file=sys.stderr)
    print(f"[*] Unique DICOM endpoints: {len(asset_db)}", file=sys.stderr)
    print()

    # Strip internal tracking field before output
    for r in asset_db.values():
        r.pop("_total_duration_ms", None)

    print_table(asset_db)

    if output_json:
        records = sorted(asset_db.values(), key=lambda r: r["ip"])
        with open(output_json, "w") as f:
            json.dump(records, f, indent=2)
        print(f"\n[*] JSON written to {output_json}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DICOM asset discovery from PCAP via nfstream"
    )
    parser.add_argument("pcap", help="Path to PCAP file")
    parser.add_argument("--output-json", metavar="FILE",
                        help="Write JSON asset table to FILE")
    parser.add_argument("--ports", default="104,2104",
                        help="Comma-separated DICOM TCP ports (default: 104,2104)")
    args = parser.parse_args()
    ports = {int(p.strip()) for p in args.ports.split(",")}
    run(args.pcap, ports, args.output_json)


if __name__ == "__main__":
    main()
