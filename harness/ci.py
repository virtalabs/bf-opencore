"""CI run monitoring, artifact download, and test report parsing."""

import contextlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CI_WATCH_TIMEOUT = 900  # 15 minutes max wait for CI


@dataclass
class TestReport:
    """Structured test results parsed from pytest-json-report."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failed_tests: list[str] = field(default_factory=list)


def _run_gh(
    args: list[str],
    *,
    check: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def wait_for_ci(repo: str, branch: str) -> int:
    """Wait for the latest CI run on a branch to complete.

    Returns the run ID.
    """
    logger.info("Waiting for CI on branch %s...", branch)

    # Get the latest run ID for this branch
    result = _run_gh(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--branch",
            branch,
            "--limit",
            "1",
            "--json",
            "databaseId,status",
        ],
        check=True,
    )
    runs = json.loads(result.stdout)
    if not runs:
        msg = f"No CI runs found for branch {branch}"
        raise RuntimeError(msg)

    run_id = runs[0]["databaseId"]
    logger.info("Found CI run %d, waiting for completion...", run_id)

    # Block until the run completes
    _run_gh(
        [
            "run",
            "watch",
            str(run_id),
            "--repo",
            repo,
            "--exit-status",
        ],
        check=False,  # don't raise on CI failure — we handle it
        timeout=CI_WATCH_TIMEOUT,
    )

    return run_id


def get_ci_status(repo: str, run_id: int) -> bool:
    """Check if a CI run passed. Returns True if successful."""
    result = _run_gh(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "conclusion",
        ],
        check=True,
    )
    data = json.loads(result.stdout)
    return data.get("conclusion") == "success"


def download_test_report(
    repo: str,
    run_id: int,
    dest: Path,
) -> Path:
    """Download the test-report artifact from a CI run.

    Returns the path to report.json.
    """
    dest.mkdir(parents=True, exist_ok=True)

    _run_gh(
        [
            "run",
            "download",
            str(run_id),
            "--repo",
            repo,
            "--name",
            "test-report",
            "--dir",
            str(dest),
        ],
        check=True,
    )

    report_path = dest / "report.json"
    if not report_path.exists():
        msg = f"test-report artifact downloaded but report.json not found in {dest}"
        raise FileNotFoundError(msg)

    logger.info("Downloaded test report to %s", report_path)
    return report_path


def get_failed_logs(repo: str, run_id: int) -> str:
    """Get the failed step logs from a CI run.

    Returns LLM-sized output from only the failed steps.
    Falls back to empty string if no failed logs available.
    """
    result = _run_gh(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--log-failed",
        ],
        check=False,
    )

    if result.returncode != 0 or not result.stdout.strip():
        logger.warning(
            "Could not retrieve failed logs for run %d",
            run_id,
        )
        return ""

    return result.stdout


def parse_test_report(report_path: Path) -> TestReport:
    """Parse a pytest-json-report file into a TestReport."""
    report: dict = {}
    with contextlib.suppress(json.JSONDecodeError):
        report = json.loads(report_path.read_text())

    if not report:
        logger.warning("Empty or invalid test report at %s", report_path)
        return TestReport()

    summary = report.get("summary", {})
    tests = report.get("tests", [])

    failed_tests = [
        test["nodeid"] for test in tests if test.get("outcome") in ("failed", "error")
    ]

    return TestReport(
        total=summary.get("total", 0),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        errors=summary.get("error", 0),
        failed_tests=failed_tests,
    )
