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
    """Transform an extract record into an Asset-shaped dict.

    Preserves all HL7 fields alongside the Asset mapping. Strict
    conformance to the Asset model happens at upsert time, not here.
    """
    return {
        # Asset-mapped fields
        "mac_address": record.get("mac_address", ""),
        "ip_address": record.get("ip_address", ""),
        "name": record.get("sending_app", ""),
        "serial_number": record.get("equipment_id", ""),
        "open_ports_tcp": [record["port"]] if record.get("port") else [],
        "source": "hl7_passive",
        # HL7 context
        "sending_facility": record.get("sending_facility", ""),
        "receiving_app": record.get("receiving_app", ""),
        "receiving_facility": record.get("receiving_facility", ""),
        "message_timestamp": record.get("message_timestamp", ""),
        "message_type": record.get("message_type", ""),
        "message_id": record.get("message_id", ""),
        "hl7_version": record.get("hl7_version", ""),
        "patient_location": record.get("patient_location", ""),
    }


def main():
    devices: set[tuple[str, str]] = set()
    count = 0

    for line in sys.stdin:
        aline = line.strip()
        if not aline:
            continue

        record = json.loads(aline)
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
