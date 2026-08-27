"""Zeek log processing for Asset ingest (conn.log + arp.log).

Reads stock Zeek conn.log plus the arp.log produced by
``blueflow/zeek/scripts/arp_extract.zeek``, aggregates per-device
payloads, and emits ``AssetUpsertSerializer``-shaped dicts.

Two consumers:

- ``blueflow.management.commands.zeek_ingest`` calls
  ``payloads_from_logdir`` in-process and upserts via the ORM.
- The docker test harness (``docker/``) runs this module as a CLI
  script (``python3 sidecar.py <logdir> --url <bf>``) to push payloads
  over HTTP to a running BlueFlow (or stub server).

The HL7-specific predecessor (sending_app -> name, equipment_id ->
serial_number, hl7_* external_keys) lives at
``blueflow.zeek.hl7.sidecar``.
"""

import argparse
import hashlib
import ipaddress
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
ZERO_MAC = "00:00:00:00:00:00"


def mac_from_ip(ip: str) -> str:
    """Synthesize a locally-administered MAC from an IP.

    Only used when Zeek runs against a pcap that lacks L2 headers (e.g.
    loopback replay) and conn.log therefore has no
    orig_l2_addr/resp_l2_addr. Live capture and Ethernet-framed pcaps
    populate real MACs and skip this path. The 02:00 prefix marks the
    MAC as locally administered. Deterministic so re-runs upsert the
    same asset.
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


def _is_device_mac(mac: str) -> bool:
    """Return True if mac names a real endpoint (not broadcast / multicast / zero)."""
    if not mac:
        return False
    normalized = mac.lower()
    if normalized == ZERO_MAC:
        return False
    try:
        first = int(normalized.split(":", 1)[0], 16)
    except ValueError:
        return False
    # IEEE I/G bit (lsb of first octet) set => multicast or broadcast.
    return (first & 1) == 0


def _is_routable_ip(ip: str) -> bool:
    """Return True if ip is something we'd record on an Asset row."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_unspecified or addr.is_multicast or addr.is_reserved)


def _observe(
    devices: dict[str, dict],
    mac: str,
    ip: str,
    port: int | None = None,
) -> None:
    """Record one endpoint observation, merging into an existing device row."""
    if _is_device_mac(mac):
        key = mac.lower()
    elif not mac and _is_routable_ip(ip):
        # No MAC at all (pcap without L2 headers) -> synthesize from IP.
        # A *present* broadcast/multicast MAC means the L2 dst was not a
        # device (e.g. UDP to ff:ff:ff:ff:ff:ff), so falling back to the
        # IP would fabricate a phantom Asset for the broadcast IP itself.
        key = mac_from_ip(ip)
    else:
        return

    dev = devices.setdefault(
        key,
        {"mac_address": key, "ip_address": "", "open_ports_tcp": set()},
    )
    if not dev["ip_address"] and _is_routable_ip(ip):
        dev["ip_address"] = ip
    if port is not None:
        dev["open_ports_tcp"].add(int(port))


def aggregate(conn_entries: list[dict], arp_entries: list[dict]) -> list[dict]:
    """Build per-device upsert payloads from conn.log + arp.log entries."""
    devices: dict[str, dict] = {}

    for entry in conn_entries:
        proto = (entry.get("proto") or "").lower()
        resp_p = entry.get("id.resp_p")
        # Originator: real endpoint, but its source port is ephemeral noise.
        _observe(
            devices,
            entry.get("orig_l2_addr", ""),
            entry.get("id.orig_h", ""),
            port=None,
        )
        # Responder: id.resp_p IS its open port (only meaningful for TCP).
        _observe(
            devices,
            entry.get("resp_l2_addr", ""),
            entry.get("id.resp_h", ""),
            port=int(resp_p) if proto == "tcp" and resp_p is not None else None,
        )

    # ARP: src side only. Request-dst is broadcast (not a device); reply-dst
    # is the original querier, already seen as the src of its own request.
    for entry in arp_entries:
        _observe(devices, entry.get("src_mac", ""), entry.get("src_ip", ""))

    return [_build_payload(dev) for dev in devices.values()]


def _build_payload(dev: dict) -> dict:
    payload = {
        "mac_address": dev["mac_address"],
        "manufacturer": "Unknown",
        "open_ports_tcp": sorted(dev["open_ports_tcp"]),
    }
    if dev["ip_address"]:
        payload["ip_address"] = dev["ip_address"]
    return payload


def payloads_from_logdir(logdir: Path) -> list[dict]:
    """Top-level: load + aggregate, return upsert payloads."""
    conn_entries = load_log(logdir / "conn.log")
    arp_entries = load_log(logdir / "arp.log")
    if not conn_entries and not arp_entries:
        return []
    return aggregate(conn_entries, arp_entries)


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


def main() -> None:
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
        print("No conn.log or arp.log entries found.")  # noqa: T201
        sys.exit(0)

    print(f"Aggregated into {len(payloads)} asset(s).\n")  # noqa: T201

    failures = 0
    for payload in payloads:
        if args.url:
            try:
                status_code = push(payload, args.url, args.token)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                failures += 1
                print(  # noqa: T201
                    f"PUT {payload['mac_address']} failed: {exc}",
                    file=sys.stderr,
                )
            else:
                print(f"PUT {payload['mac_address']} -> {status_code}")  # noqa: T201
        else:
            print(json.dumps(payload, indent=2))  # noqa: T201

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
