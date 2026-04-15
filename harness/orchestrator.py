"""CLI entry point for the agent harness orchestrator."""

import json
import logging
import sys
from pathlib import Path

import click

from harness.agents import (
    create_draft_pr,
    get_diff,
    push_branch,
    run_coder,
    run_lint,
    run_planner,
    run_reviewer,
    run_tests,
    save_output,
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
    """Execute the Planner -> Coder -> Reviewer pipeline."""
    issue = _phase_fetch(repo, issue_number)
    plan_result = _phase_plan(
        repo,
        issue_number,
        issue,
        log_dir,
    )
    if plan_result is None:
        return

    if not skip_approval and not _gate_human_approval(plan_result):
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
        plan_result,
        branch_name=branch_name,
        max_attempts=max_attempts,
        log_dir=log_dir,
    )

    if approved:
        _phase_open_pr(repo, issue_number, issue, plan_result, branch_name)


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
    """Run the Coder/Reviewer loop. Returns True if approved."""
    plan_json = json.dumps(plan, indent=2)
    feedback: str | None = None
    cwd = str(Path.cwd())

    for attempt in range(1, max_attempts + 1):
        logger.info("=== Attempt %d/%d ===", attempt, max_attempts)

        from_label = "agent-planning" if attempt == 1 else "agent-reviewing"
        approved = _single_attempt(
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

        if approved is True:
            return True
        if approved is None:
            feedback = "Previous review verdict was unparseable. Please re-review."
        else:
            feedback = approved  # rejection feedback string

        if attempt == max_attempts:
            transition(
                repo,
                issue_number,
                "agent-reviewing",
                "agent-rejected",
            )
            msg = (
                f"Agent pipeline rejected after {max_attempts} "
                f"attempts.\n\nLast feedback: {feedback}"
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
) -> bool | str | None:
    """Run one code+review cycle.

    Returns:
        True if approved, None if verdict unparseable,
        or the rejection feedback string.

    """
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

    # --- Local sensors ---
    logger.info("Running lint...")
    lint_result = run_lint(cwd)
    logger.info(
        "Lint: %s",
        "PASS" if lint_result.passed else "FAIL",
    )

    logger.info("Running tests...")
    test_result = run_tests(cwd)
    logger.info(
        "Tests: %s",
        "PASS" if test_result.passed else "FAIL",
    )

    # --- Review ---
    transition(repo, issue_number, "agent-coding", "agent-reviewing")
    diff = get_diff(cwd)
    logger.info("Starting Reviewer agent (attempt %d)...", attempt)
    review_result = run_reviewer(
        diff=diff,
        plan_json=plan_json,
        lint_output=lint_result.output,
        test_output=test_result.output,
    )
    save_output(
        issue_number,
        "reviewer",
        attempt,
        review_result.raw_output,
        log_dir,
    )

    if review_result.verdict is None:
        logger.warning("Reviewer produced no valid verdict JSON.")
        return None

    verdict = review_result.verdict.get("verdict", "reject")
    if verdict == "approve":
        logger.info("Approved on attempt %d!", attempt)
        return True

    rej = review_result.verdict.get(
        "rejection_feedback",
        "No specific feedback.",
    )
    logger.info("Rejected (attempt %d): %s", attempt, rej[:200])
    return rej


def _phase_open_pr(
    repo: str,
    issue_number: int,
    issue: dict,
    plan: dict,
    branch_name: str,
) -> None:
    """Push the branch and open a draft PR."""
    cwd = str(Path.cwd())

    logger.info("Pushing branch %s...", branch_name)
    push_branch(cwd, branch_name)

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
