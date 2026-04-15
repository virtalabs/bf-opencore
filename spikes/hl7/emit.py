#!/usr/bin/env python3
"""Conform extracted HL7 records to the BlueFlow Asset data model and print.

Reads JSON lines from stdin (produced by extract.py), maps fields to Asset
shape, and prints. In production this becomes the Celery upsert call.

Usage:
    ./extract.py <pcap> | ./emit.py
"""

import json
import sys


def map_to_asset(record: dict) -> dict:
    """Transform an extract record into an Asset-shaped dict."""
    return {
        "mac_address": record.get("mac_address", ""),
        "ip_address": record.get("ip_address", ""),
        "name": record.get("sending_app", ""),
        "serial_number": record.get("equipment_id", ""),
        "open_ports_tcp": [record["port"]] if record.get("port") else [],
        "source": "hl7_passive",
    }


def main():
    devices: set[tuple[str, str]] = set()
    count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        record = json.loads(line)
        asset = map_to_asset(record)

        count += 1
        devices.add((asset["mac_address"], asset["ip_address"]))

        print(f"--- Asset {count} ---")
        for k, v in asset.items():
            print(f"  {k}: {v}")
        print()

    print(f"Total: {count} records from {len(devices)} device(s)")


if __name__ == "__main__":
    main()
