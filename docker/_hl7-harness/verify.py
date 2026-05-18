#!/usr/bin/env python3
r"""Verify post-conditions of a docker compose harness run.

Reads the artifacts produced by the harness (Zeek logs + stub server's
JSONL ledger) and asserts:

- ``hl7.log`` row count matches ``--expect-hl7``
- ``upserts.jsonl`` row count matches ``--expect-upserts``
- Unique ``mac_address`` values across upserts == ``--expect-macs``
- Each upsert body satisfies the structural invariants the sidecar
  promises (mac_address required and non-empty, ip_address parses,
  open_ports_tcp is a list of ints in 1..65535, external_keys is dict)

Exits 0 on all-pass, 1 on any failure. Designed to be cheap to read
when it fails — every failure prints the offending row.

Usage (from repo root):
    python3 docker/verify.py /tmp/zeek-spike-logs/                # default counts
    python3 docker/verify.py /tmp/zeek-spike-logs/ \
        --expect-hl7 124 --expect-upserts 1 --expect-macs 1
"""

import argparse
import ipaddress
import json
import sys
from pathlib import Path

MAX_PORT = 65535


def fail(msg: str) -> None:
    """Print a failure to stderr without exiting (caller decides)."""
    print(f"FAIL: {msg}", file=sys.stderr)  # noqa: T201


def ok(msg: str) -> None:
    """Print a passing check to stdout."""
    print(f"OK: {msg}")  # noqa: T201


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open())


def validate_payload(body: dict) -> list[str]:
    """Return a list of human-readable issues. Empty list = valid."""
    issues: list[str] = []

    mac = body.get("mac_address")
    if not isinstance(mac, str) or not mac.strip():
        issues.append("mac_address missing or empty")

    ip = body.get("ip_address")
    if ip is not None:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            issues.append(f"ip_address not parseable: {ip!r}")

    ports = body.get("open_ports_tcp")
    if ports is not None:
        if not isinstance(ports, list):
            issues.append(f"open_ports_tcp is not a list: {type(ports).__name__}")
        else:
            for p in ports:
                if not isinstance(p, int) or not (1 <= p <= MAX_PORT):
                    issues.append(f"open_ports_tcp contains invalid port: {p!r}")
                    break

    ext = body.get("external_keys")
    if ext is not None and not isinstance(ext, dict):
        issues.append(f"external_keys is not an object: {type(ext).__name__}")

    return issues


def scan_ledger(ledger: Path) -> tuple[set[str], int]:
    """Validate every JSONL row. Return (unique MACs, failure count)."""
    macs: set[str] = set()
    failures = 0
    if not ledger.exists():
        return macs, 0
    for lineno, raw in enumerate(ledger.open(), start=1):
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(f"upserts.jsonl line {lineno}: not JSON ({exc})")
            failures += 1
            continue
        if not isinstance(entry, dict):
            fail(f"upserts.jsonl line {lineno}: row is not an object")
            failures += 1
            continue
        body = entry.get("body")
        if not isinstance(body, dict):
            fail(f"upserts.jsonl line {lineno}: body is not an object")
            failures += 1
            continue
        for issue in validate_payload(body):
            fail(f"upserts.jsonl line {lineno}: {issue}")
            failures += 1
        mac = body.get("mac_address")
        if isinstance(mac, str) and mac:
            macs.add(mac)
    return macs, failures


def check_count(label: str, actual: int, expected: int, source: Path) -> int:
    """Compare counts. Return 1 on mismatch, 0 on match."""
    if actual != expected:
        fail(f"{label}: expected {expected}, got {actual} ({source})")
        return 1
    ok(f"{label} = {actual}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logs_root",
        type=Path,
        help="Path to /tmp/zeek-spike-logs/ (or wherever logs landed)",
    )
    parser.add_argument("--expect-hl7", type=int, default=124)
    parser.add_argument("--expect-upserts", type=int, default=1)
    parser.add_argument("--expect-macs", type=int, default=1)
    args = parser.parse_args()

    hl7_log = args.logs_root / "zeek" / "hl7.log"
    ledger = args.logs_root / "blueflow" / "upserts.jsonl"

    failures = 0
    failures += check_count(
        "hl7.log row count", count_lines(hl7_log), args.expect_hl7, hl7_log
    )
    failures += check_count(
        "upserts.jsonl row count",
        count_lines(ledger),
        args.expect_upserts,
        ledger,
    )

    macs, mac_failures = scan_ledger(ledger)
    failures += mac_failures
    failures += check_count(
        "unique mac_address count", len(macs), args.expect_macs, ledger
    )

    if failures:
        print(f"\n{failures} check(s) failed.", file=sys.stderr)  # noqa: T201
        return 1

    print("\nAll checks passed.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
