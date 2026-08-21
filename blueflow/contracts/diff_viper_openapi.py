"""Classify Viper OpenAPI drift via oasdiff (breaking vs non-breaking)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HTTP_METHODS = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
)

DEFAULT_OPERATION_ID = "assets-processIntegrationCreate"


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_operation_methods(
    path_item: dict[str, Any], operation: str
) -> dict[str, Any]:
    return {
        method: op
        for method in _HTTP_METHODS
        if isinstance(op := path_item.get(method), dict)
        and op.get("operationId") == operation
    }


def slice_for_operation(
    spec: dict[str, Any],
    operation: str = DEFAULT_OPERATION_ID,
) -> dict[str, Any]:
    """Return a minimal OpenAPI spec containing only paths for *operation*."""
    sliced_paths: dict[str, Any] = {}
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        kept = _find_operation_methods(path_item, operation)
        if kept:
            if "parameters" in path_item:
                kept["parameters"] = path_item["parameters"]
            sliced_paths[path] = kept
    if not sliced_paths:
        msg = f"operationId {operation!r} not found in OpenAPI paths"
        raise ValueError(msg)
    out: dict[str, Any] = {
        "openapi": spec.get("openapi", "3.0.0"),
        "info": spec.get("info", {"title": "sliced", "version": "1"}),
        "paths": sliced_paths,
    }
    if components := spec.get("components"):
        out["components"] = components
    return out


def slice_openapi_for_operation(spec: dict[str, Any], operation: str) -> dict[str, Any]:
    """Return a minimal OpenAPI spec containing only paths for *operation*."""
    return slice_for_operation(spec, operation)


def _oasdiff_bin() -> str:
    return shutil.which("oasdiff") or "oasdiff"


def _is_oasdiff_cli_error(result: subprocess.CompletedProcess[str]) -> bool:
    combined = f"{result.stdout or ''}{result.stderr or ''}"
    lowered = combined.lower()
    return "unknown flag" in lowered or combined.startswith("Usage:")


def _run_oasdiff(
    binary: str, subcommand: str, baseline_sliced: Path, live_sliced: Path
) -> subprocess.CompletedProcess[str]:
    args = [
        binary,
        subcommand,
        str(baseline_sliced),
        str(live_sliced),
        "--format",
        "text",
    ]
    if subcommand == "breaking":
        args.extend(["--fail-on", "ERR"])
    return subprocess.run(  # noqa: S603
        args,
        check=False,
        capture_output=True,
        text=True,
    )


def _emit_process_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)


def _classify_with_oasdiff(
    binary: str,
    baseline_sliced: Path,
    live_sliced: Path,
    operation: str,
) -> int:
    try:
        breaking = _run_oasdiff(binary, "breaking", baseline_sliced, live_sliced)
        _emit_process_output(breaking)
        if _is_oasdiff_cli_error(breaking):
            sys.stderr.write("::error::oasdiff failed to run\n")
            return 2
        if breaking.returncode != 0:
            sys.stderr.write(
                f"::warning::Breaking Viper OpenAPI changes detected for {operation}\n"
            )
            return 1

        changelog = _run_oasdiff(binary, "changelog", baseline_sliced, live_sliced)
        if changelog.stderr:
            sys.stderr.write(changelog.stderr)
        if _is_oasdiff_cli_error(changelog):
            sys.stderr.write("::error::oasdiff changelog failed to run\n")
            return 2
        if changelog.stdout.strip():
            sys.stdout.write("::notice::Non-breaking Viper OpenAPI changes:\n")
            sys.stdout.write(changelog.stdout)
    except FileNotFoundError:
        sys.stderr.write(f"::error::oasdiff binary not found: {binary}\n")
        return 2
    return 0


def diff_viper_openapi(
    *,
    baseline: Path,
    live: Path,
    operation: str = DEFAULT_OPERATION_ID,
    oasdiff: str | None = None,
) -> int:
    """Compare baseline vs live OpenAPI specs for breaking changes.

    Returns 0 when there is no baseline (bootstrap), no breaking changes, or
    oasdiff reports only safe changes. Returns 1 when breaking changes exist.
    Returns 2 when oasdiff fails to run.
    """
    if not baseline.is_file():
        sys.stdout.write(
            f"::notice::No prior Viper OpenAPI baseline at {baseline} — "
            "seeding from live fetch on this run\n"
        )
        return 0

    if not live.is_file():
        sys.stderr.write(f"Live OpenAPI spec not found: {live}\n")
        return 2

    binary = oasdiff or _oasdiff_bin()
    try:
        baseline_spec = slice_openapi_for_operation(load_spec(baseline), operation)
        live_spec = slice_openapi_for_operation(load_spec(live), operation)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Invalid OpenAPI JSON: {exc}\n")
        return 2
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    with tempfile.TemporaryDirectory(prefix="viper-openapi-") as tmp:
        tmpdir = Path(tmp)
        baseline_sliced = tmpdir / "baseline.json"
        live_sliced = tmpdir / "live.json"
        baseline_sliced.write_text(
            json.dumps(baseline_spec, indent=2), encoding="utf-8"
        )
        live_sliced.write_text(json.dumps(live_spec, indent=2), encoding="utf-8")

        result = _classify_with_oasdiff(binary, baseline_sliced, live_sliced, operation)
        if result != 0:
            return result

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
        default=DEFAULT_OPERATION_ID,
        help="operationId to scope the diff",
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
