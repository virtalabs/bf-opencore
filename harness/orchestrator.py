"""CLI entry point for the agent harness orchestrator."""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click

from harness.agents import (
    SensorResult,
    create_draft_pr,
    get_changed_files,
    get_diff,
    push_branch,
    run_code_review,
    run_coder,
    run_lint,
    run_planner,
    save_output,
)
from harness.ci import (
    TestReport,
    download_test_report,
    get_ci_status,
    get_failed_logs,
    parse_test_report,
    wait_for_ci,
)
from harness.state import (
    comment_on_issue,
    derive_branch_name,
    detect_repo,
    fetch_issue,
    list_eligible,
    setup_labels,
    transition,
)

logger = logging.getLogger("harness")

BASELINE_PATH = Path(__file__).parent / "baseline.json"


@dataclass
class Verdict:
    """Deterministic verdict assembled from sensors + code review."""

    approved: bool
    reasons: list[str] = field(default_factory=list)
    ci_run_id: int | None = None
    findings: list[dict] = field(default_factory=list)


def _setup_logging(log_dir: Path, issue_number: int) -> None:
    """Configure console + file logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"issue-{issue_number}" / "orchestrator.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
    logger.addHandler(console)
    logger.addHandler(file_handler)


@click.group()
def cli() -> None:
    """Blueflow agent harness orchestrator."""


@cli.command("setup-labels")
def setup_labels_cmd() -> None:
    """Create all agent-* labels on the GitHub repo (idempotent)."""
    repo = detect_repo()
    click.echo(f"Setting up labels on {repo}...")
    setup_labels(repo)
    click.echo("Labels created successfully.")


@cli.command("list-eligible")
def list_eligible_cmd() -> None:
    """List issues labeled agent-ready."""
    repo = detect_repo()
    issues = list_eligible(repo)

    if not issues:
        click.echo("No eligible issues found.")
        return

    click.echo(f"{'#':<6} Title")
    click.echo("-" * 60)
    for issue in issues:
        click.echo(f"{issue['number']:<6} {issue['title']}")


@cli.command()
@click.argument("issue_number", type=int)
@click.option("--max-attempts", default=3, help="Max coder/reviewer cycles.")
@click.option(
    "--skip-approval",
    is_flag=True,
    help="Skip human plan approval gate.",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    default=Path(__file__).parent / ".logs",
    help="Directory for agent output logs.",
)
def run(
    issue_number: int,
    max_attempts: int,
    *,
    skip_approval: bool,
    log_dir: Path,
) -> None:
    """Run the full agent pipeline for a GitHub issue."""
    _setup_logging(log_dir, issue_number)
    repo = detect_repo()

    try:
        _run_pipeline(
            repo,
            issue_number,
            max_attempts=max_attempts,
            skip_approval=skip_approval,
            log_dir=log_dir,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Pipeline failed with unexpected error")
        _fail(repo, issue_number, None, f"Unexpected error: {exc}")
        sys.exit(1)


def _run_pipeline(
    repo: str,
    issue_number: int,
    *,
    max_attempts: int,
    skip_approval: bool,
    log_dir: Path,
) -> None:
    """Execute the Planner -> Coder -> CI -> Review pipeline."""
    issue = _phase_fetch(repo, issue_number)
    plan = _phase_plan(repo, issue_number, issue, log_dir)
    if plan is None:
        return

    if not skip_approval and not _gate_human_approval(plan):
        _fail(
            repo,
            issue_number,
            "agent-planning",
            "Plan rejected by human.",
        )
        return

    branch_name = derive_branch_name(issue)
    logger.info("Branch: %s", branch_name)

    approved = _phase_code_review_loop(
        repo,
        issue_number,
        plan,
        branch_name=branch_name,
        max_attempts=max_attempts,
        log_dir=log_dir,
    )

    if approved:
        _phase_open_pr(repo, issue_number, issue, plan, branch_name)


def _phase_fetch(repo: str, issue_number: int) -> dict:
    """Fetch the issue from GitHub."""
    logger.info("Fetching issue #%d from %s", issue_number, repo)
    issue = fetch_issue(repo, issue_number)
    logger.info("Issue: %s", issue["title"])
    return issue


def _phase_plan(
    repo: str,
    issue_number: int,
    issue: dict,
    log_dir: Path,
) -> dict | None:
    """Run the Planner agent and return the plan, or None on failure."""
    logger.info("Starting Planner agent...")
    transition(repo, issue_number, "agent-ready", "agent-planning")

    issue_context = json.dumps(issue, indent=2)
    plan_result = run_planner(issue_context)
    save_output(
        issue_number,
        "planner",
        1,
        plan_result.raw_output,
        log_dir,
    )

    if plan_result.plan is None:
        _fail(
            repo,
            issue_number,
            "agent-planning",
            "Planner produced no valid JSON plan.",
        )
        return None

    classification = plan_result.plan.get("classification")
    logger.info("Plan received. Classification: %s", classification)
    return plan_result.plan


def _gate_human_approval(plan: dict) -> bool:
    """Display the plan and prompt for human approval."""
    click.echo("\n--- Proposed Plan ---")
    click.echo(json.dumps(plan, indent=2))
    click.echo("--- End Plan ---\n")
    return click.confirm("Approve this plan?")


def _phase_code_review_loop(
    repo: str,
    issue_number: int,
    plan: dict,
    *,
    branch_name: str,
    max_attempts: int,
    log_dir: Path,
) -> bool:
    """Run the Coder/CI/Review loop. Returns True if approved."""
    plan_json = json.dumps(plan, indent=2)
    feedback: str | None = None
    cwd = str(Path.cwd())

    for attempt in range(1, max_attempts + 1):
        logger.info("=== Attempt %d/%d ===", attempt, max_attempts)

        from_label = "agent-planning" if attempt == 1 else "agent-reviewing"
        verdict = _single_attempt(
            repo,
            issue_number,
            plan_json,
            branch_name=branch_name,
            attempt=attempt,
            from_label=from_label,
            feedback=feedback,
            cwd=cwd,
            log_dir=log_dir,
        )

        if verdict.approved:
            return True

        feedback = "\n".join(verdict.reasons)
        if verdict.findings:
            feedback += "\n\nCode review findings:\n"
            for finding in verdict.findings:
                feedback += (
                    f"- [{finding.get('severity')}] "
                    f"{finding.get('file', '?')}:"
                    f"{finding.get('line', '?')} "
                    f"{finding.get('message', '')}\n"
                )

        logger.info(
            "Rejected (attempt %d): %s",
            attempt,
            feedback[:200],
        )

        if attempt == max_attempts:
            transition(
                repo,
                issue_number,
                "agent-reviewing",
                "agent-rejected",
            )
            msg = (
                f"Agent pipeline rejected after {max_attempts} "
                f"attempts.\n\nLast feedback:\n{feedback}"
            )
            comment_on_issue(repo, issue_number, msg)
            return False

    return False


def _single_attempt(
    repo: str,
    issue_number: int,
    plan_json: str,
    *,
    branch_name: str,
    attempt: int,
    from_label: str,
    feedback: str | None,
    cwd: str,
    log_dir: Path,
) -> Verdict:
    """Run one code + CI + review cycle. Returns a Verdict."""
    # --- Code ---
    transition(repo, issue_number, from_label, "agent-coding")
    logger.info("Starting Coder agent (attempt %d)...", attempt)
    coder_result = run_coder(
        plan_json,
        branch_name,
        feedback=feedback,
        cwd=cwd,
    )
    save_output(
        issue_number,
        "coder",
        attempt,
        coder_result.raw_output,
        log_dir,
    )

    # --- Local lint sensor (changed files only) ---
    changed_files = get_changed_files(cwd)
    logger.info("Running lint on %d changed files...", len(changed_files))
    lint_result = run_lint(cwd, changed_files=changed_files)
    logger.info(
        "Lint: %s",
        "PASS" if lint_result.passed else "FAIL",
    )

    # --- Push + CI ---
    logger.info("Pushing branch %s...", branch_name)
    push_branch(cwd, branch_name)
    transition(
        repo,
        issue_number,
        "agent-coding",
        "agent-ci-pending",
    )

    logger.info("Waiting for CI...")
    run_id = wait_for_ci(repo, branch_name)
    ci_passed = get_ci_status(repo, run_id)
    logger.info("CI: %s (run %d)", "PASS" if ci_passed else "FAIL", run_id)

    # --- Download + parse test report ---
    report_dest = log_dir / f"issue-{issue_number}" / f"ci-{attempt}"
    test_report = _fetch_test_report(repo, run_id, report_dest)

    ci_failure_log = ""
    if not ci_passed:
        ci_failure_log = get_failed_logs(repo, run_id)
        save_output(
            issue_number,
            "ci-failed-logs",
            attempt,
            ci_failure_log,
            log_dir,
        )

    # --- Code review (LLM — diff + plan only) ---
    transition(
        repo,
        issue_number,
        "agent-ci-pending",
        "agent-reviewing",
    )
    diff = get_diff(cwd)
    logger.info("Starting code review agent (attempt %d)...", attempt)
    review_result = run_code_review(diff=diff, plan_json=plan_json)
    save_output(
        issue_number,
        "code-review",
        attempt,
        review_result.raw_output,
        log_dir,
    )

    # --- Assemble verdict (deterministic) ---
    return _assemble_verdict(
        lint_result=lint_result,
        test_report=test_report,
        ci_passed=ci_passed,
        ci_failure_log=ci_failure_log,
        ci_run_id=run_id,
        findings=review_result.findings,
    )


def _fetch_test_report(
    repo: str,
    run_id: int,
    dest: Path,
) -> TestReport:
    """Download and parse the CI test report artifact."""
    try:
        report_path = download_test_report(repo, run_id, dest)
        report = parse_test_report(report_path)
        logger.info(
            "Tests: %d passed, %d failed, %d errors (of %d total)",
            report.passed,
            report.failed,
            report.errors,
            report.total,
        )
    except (FileNotFoundError, RuntimeError):
        logger.warning("Could not download test report artifact")
        report = TestReport()
    return report


def _load_baseline() -> dict:
    """Load the known-failure baseline from harness/baseline.json."""
    if not BASELINE_PATH.exists():
        logger.warning("No baseline file found at %s", BASELINE_PATH)
        return {}
    return json.loads(BASELINE_PATH.read_text())


def _assemble_verdict(
    *,
    lint_result: SensorResult,
    test_report: TestReport,
    ci_passed: bool,
    ci_failure_log: str,
    ci_run_id: int,
    findings: list[dict] | None,
) -> Verdict:
    """Build a deterministic verdict from sensors + code review."""
    reasons: list[str] = []
    baseline = _load_baseline()
    known_failures = set(baseline.get("test_failures", []))

    # Lint sensor (scoped to changed files only, so no baseline needed)
    if not lint_result.passed:
        reasons.append(
            f"Lint failed (ruff check rc={lint_result.details.get('check_rc')}, "
            f"ruff format rc={lint_result.details.get('format_rc')})\n"
            f"{lint_result.output[:500]}"
        )

    # CI / test sensor — only flag NEW failures not in baseline
    new_failures = [t for t in test_report.failed_tests if t not in known_failures]
    if new_failures:
        reasons.append(
            f"{len(new_failures)} NEW test failure(s) "
            f"(not in baseline):\n" + "\n".join(new_failures[:20])
        )
    if test_report.failed_tests and not new_failures:
        logger.info(
            "All %d test failures are in the known baseline — not blocking.",
            len(test_report.failed_tests),
        )

    # CI failure without test report context
    if not ci_passed and not test_report.failed_tests:
        if ci_failure_log:
            reasons.append(f"CI failed (run {ci_run_id}):\n{ci_failure_log[:1000]}")
        else:
            reasons.append(f"CI failed (run {ci_run_id})")

    # Code review findings
    blockers = [f for f in (findings or []) if f.get("severity") == "blocker"]
    reasons.extend(
        f"Blocker: {b.get('file', '?')}:"
        f"{b.get('line', '?')} — "
        f"{b.get('message', 'no message')}"
        for b in blockers
    )

    approved = len(reasons) == 0
    return Verdict(
        approved=approved,
        reasons=reasons,
        ci_run_id=ci_run_id,
        findings=findings or [],
    )


def _phase_open_pr(
    repo: str,
    issue_number: int,
    issue: dict,
    plan: dict,
    branch_name: str,
) -> None:
    """Open a draft PR (branch already pushed during CI phase)."""
    logger.info("Creating draft PR...")
    pr_url = create_draft_pr(repo, branch_name, issue, plan)
    transition(
        repo,
        issue_number,
        "agent-reviewing",
        "agent-pr-open",
    )
    comment_on_issue(
        repo,
        issue_number,
        f"Draft PR created: {pr_url}",
    )

    logger.info("Draft PR: %s", pr_url)
    click.echo(f"\nDraft PR created: {pr_url}")


def _fail(
    repo: str,
    issue_number: int,
    from_label: str | None,
    message: str,
) -> None:
    """Transition to agent-failed and comment on the issue."""
    logger.error("FAILED: %s", message)
    try:
        if from_label:
            transition(
                repo,
                issue_number,
                from_label,
                "agent-failed",
            )
        comment_on_issue(
            repo,
            issue_number,
            f"Agent pipeline failed: {message}",
        )
    except Exception:
        logger.exception(
            "Failed to update issue state during error handling",
        )


if __name__ == "__main__":
    cli()
