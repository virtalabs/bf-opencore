"""Zeek log processing for Asset ingest.

Reads Zeek JSON logs (hl7.log + conn.log), correlates entries by connection
UID, and aggregates them into per-device payloads compatible with
``AssetUpsertSerializer``.

Two consumers:

- ``blueflow.management.commands.zeek_ingest`` calls ``payloads_from_logdir``
  in-process and upserts via the ORM.
- The docker test harness (``docker/``) runs this module as a CLI script
  (``python3 sidecar.py <logdir> --url <bf>``) to push payloads over HTTP
  to a running BlueFlow (or stub server). This path is preserved for the
  end-to-end pipeline test.

Promoted from spike #111 (frozen at tag ``zeek-hl7-spike-frozen``).
"""

import argparse
import hashlib
import ipaddress
import json
import sys
import urllib.request
from pathlib import Path

SCALAR_FIELDS = (
    ("name", "sending_app"),
    ("serial_number", "equipment_id"),
    ("sending_facility", "sending_facility"),
    ("receiving_app", "receiving_app"),
    ("hl7_version", "hl7_version"),
)


def mac_from_ip(ip: str) -> str:
    """Synthesize a locally-administered MAC from a source IP.

    Used only when Zeek runs against pcap files (pcap replay carries no L2).
    Live capture populates ``conn.log`` ``orig_l2_addr`` / ``resp_l2_addr``
    with real MACs and this fallback is not exercised. The 02:00 prefix
    marks the MAC as locally administered, avoiding collision with real
    OUI-assigned MACs. Deterministic so re-runs upsert the same asset.

    IPv4 inputs map directly to the 4-byte packed form (preserves the
    readable ``02:00:c0:a8:38:01`` style for ``192.168.56.1``). IPv6 and
    other non-v4 strings hash to a stable 4-byte suffix so the contract
    holds for any input Zeek can emit.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        suffix = hashlib.sha256(ip.encode()).digest()[:4]
    else:
        suffix = (
            addr.packed
            if isinstance(addr, ipaddress.IPv4Address)
            else hashlib.sha256(addr.packed).digest()[:4]
        )
    return f"02:00:{suffix[0]:02x}:{suffix[1]:02x}:{suffix[2]:02x}:{suffix[3]:02x}"


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


def push(payload: dict, base_url: str, token: str | None) -> int:
    """PUT payload to the upsert endpoint. Returns HTTP status code."""
    url = f"{base_url.rstrip('/')}/api/assets/upsert/"
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    req = urllib.request.Request(  # noqa: S310
        url, data=data, headers=headers, method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return resp.status


def main():
    """CLI entry point used by the docker harness."""
    parser = argparse.ArgumentParser(description="Zeek log sidecar for BlueFlow")
    parser.add_argument("logdir", type=Path, help="Zeek JSON log directory")
    parser.add_argument("--url", help="BlueFlow base URL (omit for dry-run)")
    parser.add_argument("--token", help="API token for authentication")
    args = parser.parse_args()

    if not args.logdir.is_dir():
        print(  # noqa: T201
            f"Error: not a directory: {args.logdir}",
            file=sys.stderr,
        )
        sys.exit(1)

    payloads = payloads_from_logdir(args.logdir)
    if not payloads:
        print("No HL7 log entries found.")  # noqa: T201
        sys.exit(0)

    print(f"Aggregated into {len(payloads)} asset(s).\n")  # noqa: T201

    for payload in payloads:
        if args.url:
            status_code = push(payload, args.url, args.token)
            print(f"PUT {payload['mac_address']} -> {status_code}")  # noqa: T201
        else:
            print(json.dumps(payload, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
