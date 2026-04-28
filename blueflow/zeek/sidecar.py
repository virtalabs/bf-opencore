"""Zeek log processing for Asset ingest.

Reads Zeek JSON logs (hl7.log + conn.log), correlates entries by connection
UID, and aggregates them into per-device payloads compatible with
``AssetUpsertSerializer``.

Promoted from spike #111 (frozen at tag ``zeek-hl7-spike-frozen``).
"""

import json
from pathlib import Path

SCALAR_FIELDS = (
    ("name", "sending_app"),
    ("serial_number", "equipment_id"),
    ("sending_facility", "sending_facility"),
    ("receiving_app", "receiving_app"),
    ("hl7_version", "hl7_version"),
)


def mac_from_ip(ip: str) -> str:
    """Synthesize a locally-administered MAC from an IPv4 address.

    Used only when Zeek runs against pcap files (pcap replay carries no L2).
    Live capture populates ``conn.log`` ``orig_l2_addr`` / ``resp_l2_addr``
    with real MACs and this fallback is not exercised. The 02:00 prefix
    marks the MAC as locally administered, avoiding collision with real
    OUI-assigned MACs. Deterministic so re-runs upsert the same asset.
    """
    octets = [int(o) for o in ip.split(".")]
    return f"02:00:{octets[0]:02x}:{octets[1]:02x}:{octets[2]:02x}:{octets[3]:02x}"


def load_log(path: Path) -> list[dict]:
    """Read a Zeek JSON log file. Skip comment lines, return list of dicts."""
    if not path.exists():
        return []
    entries = []
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(json.loads(stripped))
    return entries


def correlate(hl7_entries: list[dict], conn_entries: list[dict]) -> list[dict]:
    """Join hl7 entries with conn entries on ``uid`` to enrich with L2."""
    conn_by_uid = {e["uid"]: e for e in conn_entries}
    for entry in hl7_entries:
        conn = conn_by_uid.get(entry.get("uid"))
        if conn:
            for field in ("orig_l2_addr", "resp_l2_addr"):
                if field in conn:
                    entry[field] = conn[field]
    return hl7_entries


def _init_device(mac: str, orig_h: str) -> dict:
    """Create a new device accumulator."""
    return {
        "mac_address": mac or mac_from_ip(orig_h),
        "ip_address": orig_h,
        "name": "",
        "serial_number": "",
        "open_ports_tcp": set(),
        "message_types": set(),
        "sending_facility": "",
        "receiving_app": "",
        "hl7_version": "",
    }


def _build_payload(dev: dict) -> dict:
    """Convert a device accumulator into an upsert payload."""
    payload = {
        "mac_address": dev["mac_address"],
        "ip_address": dev["ip_address"],
        "name": dev["name"],
        "open_ports_tcp": sorted(dev["open_ports_tcp"]),
        "external_keys": {
            "hl7_sending_facility": dev["sending_facility"],
            "hl7_receiving_app": dev["receiving_app"],
            "hl7_message_types": sorted(dev["message_types"]),
            "hl7_version": dev["hl7_version"],
        },
    }
    if dev["serial_number"]:
        payload["serial_number"] = dev["serial_number"]
    return payload


def aggregate(entries: list[dict]) -> list[dict]:
    """Group entries by device, produce one upsert payload per device."""
    devices: dict[str, dict] = {}

    for entry in entries:
        orig_h = entry.get("id.orig_h", "")
        resp_p = entry.get("id.resp_p")
        mac = entry.get("orig_l2_addr", "")
        device_key = mac or orig_h

        if not device_key:
            continue

        if device_key not in devices:
            devices[device_key] = _init_device(mac, orig_h)

        dev = devices[device_key]

        for dev_field, entry_field in SCALAR_FIELDS:
            if not dev[dev_field] and entry.get(entry_field):
                dev[dev_field] = entry[entry_field]

        if resp_p is not None:
            dev["open_ports_tcp"].add(int(resp_p))
        if entry.get("message_type"):
            dev["message_types"].add(entry["message_type"])

    return [_build_payload(dev) for dev in devices.values()]


def payloads_from_logdir(logdir: Path) -> list[dict]:
    """Top-level: load + correlate + aggregate, return upsert payloads."""
    hl7_entries = load_log(logdir / "hl7.log")
    if not hl7_entries:
        return []
    conn_entries = load_log(logdir / "conn.log")
    enriched = correlate(hl7_entries, conn_entries)
    return aggregate(enriched)
