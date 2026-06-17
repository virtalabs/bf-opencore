"""Classify Viper OpenAPI drift via oasdiff (breaking vs non-breaking)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _oasdiff_bin() -> str:
    return shutil.which("oasdiff") or "oasdiff"


def diff_viper_openapi(
    *,
    baseline: Path,
    live: Path,
    operation: str = "integrationUpload",
    oasdiff: str | None = None,
) -> int:
    """Compare baseline vs live OpenAPI specs for breaking changes.

    Returns 0 when there is no baseline (bootstrap), no breaking changes, or
    oasdiff reports only safe changes. Returns 1 when breaking changes exist.
    """
    if not baseline.is_file():
        sys.stdout.write(
            f"::notice::No prior Viper OpenAPI baseline at {baseline} — "
            "seeding from live fetch on this run\n"
        )
        return 0

    if not live.is_file():
        sys.stderr.write(f"Live OpenAPI spec not found: {live}\n")
        return 1

    binary = oasdiff or _oasdiff_bin()
    op_filter = f"operationId:{operation}"
    breaking = subprocess.run(  # noqa: S603
        [
            binary,
            "breaking",
            str(baseline),
            str(live),
            "--filter",
            op_filter,
            "--format",
            "text",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if breaking.stdout:
        sys.stdout.write(breaking.stdout)
    if breaking.stderr:
        sys.stderr.write(breaking.stderr)

    if breaking.returncode != 0:
        sys.stderr.write(
            "::warning::Breaking Viper OpenAPI changes detected "
            f"for {operation}\n"
        )
        return 1

    changelog = subprocess.run(  # noqa: S603
        [
            binary,
            "changelog",
            str(baseline),
            str(live),
            "--filter",
            op_filter,
            "--format",
            "text",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if changelog.stdout.strip():
        sys.stdout.write("::notice::Non-breaking Viper OpenAPI changes:\n")
        sys.stdout.write(changelog.stdout)
    if changelog.stderr:
        sys.stderr.write(changelog.stderr)

    sys.stdout.write("No breaking Viper OpenAPI changes detected\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify Viper OpenAPI drift with oasdiff"
    )
    parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Path to baseline openapi.json from prior drift run",
    )
    parser.add_argument(
        "--live", required=True, type=Path, help="Path to live-fetched openapi.json"
    )
    parser.add_argument(
        "--operation",
        default="integrationUpload",
        help="operationId filter passed to oasdiff",
    )
    parser.add_argument(
        "--oasdiff",
        default=None,
        help="Path to oasdiff binary (default: search PATH)",
    )
    args = parser.parse_args(argv)
    return diff_viper_openapi(
        baseline=args.baseline,
        live=args.live,
        operation=args.operation,
        oasdiff=args.oasdiff,
    )


if __name__ == "__main__":
    raise SystemExit(main())
