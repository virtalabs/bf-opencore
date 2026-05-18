#!/usr/bin/env python3
"""Stub HTTP server that accepts any request and dumps it to stdout.

Stands in for the BlueFlow upsert endpoint during prototype testing.
No Django, no database — just prints what it receives, appends a
machine-readable JSONL line to /logs/upserts.jsonl, and returns 200.

Usage:
    python3 stub_server.py           # listens on :8000
    python3 stub_server.py 9999      # listens on :9999

Override ledger path via STUB_LEDGER_PATH env var (default /logs/upserts.jsonl).
The ledger is what docker/verify.py reads to assert post-conditions.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LEDGER_PATH = Path(os.environ.get("STUB_LEDGER_PATH", "/logs/upserts.jsonl"))


class Handler(BaseHTTPRequestHandler):
    """Accepts any PUT/POST request and dumps the body to stdout."""

    def do_PUT(self):
        """Handle PUT requests."""
        self._handle()

    def do_POST(self):
        """Handle POST requests."""
        self._handle()

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        print(f"\n{'=' * 60}")  # noqa: T201
        print(f"{self.command} {self.path}")  # noqa: T201
        ct = self.headers.get("Content-Type", "(none)")
        print(f"Content-Type: {ct}")  # noqa: T201
        if self.headers.get("Authorization"):
            auth = self.headers["Authorization"]
            print(f"Authorization: {auth}")  # noqa: T201

        parsed_body = None
        if body:
            try:
                parsed_body = json.loads(body)
                print(json.dumps(parsed_body, indent=2))  # noqa: T201
            except json.JSONDecodeError:
                decoded = body.decode("utf-8", errors="replace")
                print(decoded)  # noqa: T201
        print(f"{'=' * 60}")  # noqa: T201

        self._append_ledger(parsed_body)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def _append_ledger(self, parsed_body):
        """Append one JSONL row per request for downstream verification."""
        try:
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "method": self.command,
                "path": self.path,
                "body": parsed_body,
            }
            with LEDGER_PATH.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            print(f"WARN: ledger write failed: {exc}", file=sys.stderr)  # noqa: T201

    def log_message(self, _format, *_args):
        """Suppress default stderr logging — we print to stdout."""


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("", port), Handler)
    print(f"Stub server listening on :{port}")  # noqa: T201
    print("Press Ctrl+C to stop.\n")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")  # noqa: T201


if __name__ == "__main__":
    main()
