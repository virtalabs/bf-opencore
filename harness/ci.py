"""CI run monitoring and test output parsing."""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CI_WATCH_TIMEOUT = 900  # 15 minutes max wait for CI


@dataclass
class TestReport:
    """Structured test results parsed from pytest console output."""

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

    _run_gh(
        [
            "run",
            "watch",
            str(run_id),
            "--repo",
            repo,
            "--exit-status",
        ],
        check=False,
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


def parse_test_output(output: str) -> TestReport:
    """Parse pytest's -q --tb=no output into a TestReport.

    Expects output shaped like:
        FAILED path/to/test.py::test_name
        FAILED path/to/test.py::test_other - Error...
        68 failed, 249 passed, 4 skipped, 25 xfailed in 11.52s

    This replaces pytest-json-report, which is incompatible with
    pytest-xdist (xdist workers crash serializing Django WSGIRequest
    objects through execnet when tests fail).
    """
    failed_tests = [
        match.group(1)
        for match in re.finditer(
            r"^FAILED\s+(\S+)",
            output,
            re.MULTILINE,
        )
    ]

    # Parse the summary line: "68 failed, 249 passed, ..."
    total = 0
    passed = 0
    failed = 0
    errors = 0

    summary_match = re.search(
        r"(\d+\s+\w+(?:,\s*\d+\s+\w+)*)\s+in\s+[\d.]+s",
        output,
    )
    if summary_match:
        summary_text = summary_match.group(1)
        for count_match in re.finditer(r"(\d+)\s+(\w+)", summary_text):
            count = int(count_match.group(1))
            label = count_match.group(2)
            if label == "passed":
                passed = count
            elif label == "failed":
                failed = count
            elif label in ("error", "errors"):
                errors = count
            total += count

    return TestReport(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        failed_tests=failed_tests,
    )
