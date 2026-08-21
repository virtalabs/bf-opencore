#!/usr/bin/env python3
"""Extract enriched HL7 records from a pcap file.

Runs tcpflow (TCP stream reassembly) and tshark (MAC-IP mapping) internally,
parses MLLP-framed HL7 messages, correlates network-layer identity, and emits
one JSON line per message to stdout.

Usage:
    ./extract.py <pcap_file>
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import hl7

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"

# tcpflow names files like: 192.168.056.001.59185-192.168.056.001.42042
TCPFLOW_RE = re.compile(
    r"(\d{3}\.\d{3}\.\d{3}\.\d{3})\.(\d{5})-(\d{3}\.\d{3}\.\d{3}\.\d{3})\.(\d{5})"
)


def run_tcpflow(pcap: str, outdir: str) -> None:
    subprocess.run(
        ["tcpflow", "-r", pcap, "-o", outdir],
        check=True,
        capture_output=True,
    )


def build_mac_map(pcap: str) -> dict[str, str]:
    """Run tshark and return {ip: mac} from Ethernet headers."""
    result = subprocess.run(
        [
            "tshark",
            "-r",
            pcap,
            "-T",
            "fields",
            "-e",
            "eth.src",
            "-e",
            "ip.src",
            "-Y",
            "ip.src",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0]:
            mac, ip = parts
            mapping[ip] = mac
    return mapping


def parse_tcpflow_filename(name: str) -> tuple[str, int, str, int] | None:
    """Extract (src_ip, src_port, dst_ip, dst_port) from a tcpflow filename.

    Converts zero-padded octets to normal IPs: 192.168.056.001 -> 192.168.56.1
    """
    match = TCPFLOW_RE.fullmatch(name)
    if not match:
        return None
    src_raw, src_port, dst_raw, dst_port = match.groups()
    src_ip = ".".join(str(int(o)) for o in src_raw.split("."))
    dst_ip = ".".join(str(int(o)) for o in dst_raw.split("."))
    return src_ip, int(src_port), dst_ip, int(dst_port)


def extract_messages(stream_data: bytes) -> list[str]:
    """Scan raw bytes for MLLP frames and return decoded HL7 message strings."""
    messages = []
    pos = 0
    while pos < len(stream_data):
        start = stream_data.find(MLLP_START, pos)
        if start == -1:
            break
        end = stream_data.find(MLLP_END, start + 1)
        if end == -1:
            break
        raw = stream_data[start + 1 : end].decode("ascii", errors="replace")
        messages.append(raw)
        pos = end + len(MLLP_END)
    return messages


def _field(msg: hl7.Message, segment_id: str, field_num: int) -> str:
    try:
        seg = msg.segment(segment_id)
        return str(seg(field_num))
    except (KeyError, IndexError):
        return ""


def parse_message(raw: str) -> dict:
    """Parse a raw HL7 string into a dict of extracted fields."""
    msg = hl7.parse(raw)
    return {
        "sending_app": _field(msg, "MSH", 3),
        "sending_facility": _field(msg, "MSH", 4),
        "receiving_app": _field(msg, "MSH", 5),
        "receiving_facility": _field(msg, "MSH", 6),
        "message_timestamp": _field(msg, "MSH", 7),
        "message_type": _field(msg, "MSH", 9),
        "message_id": _field(msg, "MSH", 10),
        "hl7_version": _field(msg, "MSH", 12),
        "patient_location": _field(msg, "PV1", 3),
        "equipment_id": _field(msg, "OBX", 18),
    }


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pcap_file>", file=sys.stderr)
        sys.exit(1)

    pcap = sys.argv[1]
    if not Path(pcap).is_file():
        print(f"Error: pcap file not found: {pcap}", file=sys.stderr)
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="hl7_extract_")
    try:
        run_tcpflow(pcap, tmpdir)
        mac_map = build_mac_map(pcap)

        for path in sorted(Path(tmpdir).iterdir()):
            if not path.is_file() or path.name.startswith("report."):
                continue

            parsed = parse_tcpflow_filename(path.name)
            if not parsed:
                continue

            src_ip, src_port, _, _ = parsed
            mac_address = mac_map.get(src_ip, "")

            stream_data = path.read_bytes()
            raw_messages = extract_messages(stream_data)

            for raw in raw_messages:
                record = parse_message(raw)
                if record["message_type"] == "ACK":
                    continue
                record["mac_address"] = mac_address
                record["ip_address"] = src_ip
                record["port"] = src_port
                print(json.dumps(record))
    finally:
        # Clean up temp files
        for path in Path(tmpdir).iterdir():
            path.unlink(missing_ok=True)
        Path(tmpdir).rmdir()


if __name__ == "__main__":
    main()
