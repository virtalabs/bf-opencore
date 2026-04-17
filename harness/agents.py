"""Agent invocation via Claude CLI subprocess and output parsing."""

import contextlib
import json
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

HARNESS_DIR = Path(__file__).parent
PROMPTS_DIR = HARNESS_DIR / "prompts"
DEFAULT_LOG_DIR = HARNESS_DIR / ".logs"

PLANNER_TIMEOUT = 300
CODER_TIMEOUT = 600
CODER_STALL_TIMEOUT = 120  # kill if no stdout activity for this long
CODE_REVIEW_TIMEOUT = 300
LINT_TIMEOUT = 60

MAX_PR_TITLE_LENGTH = 70


@dataclass
class PlanResult:
    raw_output: str
    plan: dict | None


@dataclass
class CoderResult:
    raw_output: str
    branch: str


@dataclass
class CodeReviewResult:
    raw_output: str
    findings: list[dict] | None


@dataclass
class SensorResult:
    passed: bool
    output: str
    details: dict = field(default_factory=dict)


class AgentStalledError(Exception):
    """Raised when an agent produces no output for too long."""

    def __init__(
        self,
        agent: str,
        seconds: int,
        partial_stdout: str,
        partial_stderr: str,
    ) -> None:
        self.agent = agent
        self.seconds = seconds
        self.partial_stdout = partial_stdout
        self.partial_stderr = partial_stderr
        msg = f"{agent} stalled — no output for {seconds}s"
        super().__init__(msg)


def _recover_stdout(exc: subprocess.TimeoutExpired) -> str:
    """Extract any partial stdout captured before a timeout."""
    out = exc.stdout or b""
    return out.decode() if isinstance(out, bytes) else out


def extract_json(text: str) -> dict | None:
    """Extract a JSON object from agent output.

    Handles both ```json fenced blocks and raw JSON.
    """
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        with contextlib.suppress(json.JSONDecodeError):
            return json.loads(match.group(1))

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        with contextlib.suppress(json.JSONDecodeError):
            return json.loads(match.group(0))

    return None


def load_prompt(name: str) -> str:
    """Load a prompt template from harness/prompts/{name}.md."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text()


def save_output(
    issue_number: int,
    agent: str,
    attempt: int | str,
    content: str,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> Path:
    """Save raw agent output to the log directory."""
    issue_dir = log_dir / f"issue-{issue_number}"
    issue_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{agent}-attempt-{attempt}.txt"
    output_path = issue_dir / filename
    output_path.write_text(content)
    logger.debug("Saved %s output to %s", agent, output_path)
    return output_path


def run_planner(issue_context: str) -> PlanResult:
    """Invoke the Planner agent to produce an implementation plan."""
    template = load_prompt("planner")
    prompt = template.replace("{issue}", issue_context)

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--allowedTools",
                "Read",
                "Glob",
                "Grep",
                "Bash(git log:*)",
                "--max-budget-usd",
                "5",
            ],
            capture_output=True,
            text=True,
            timeout=PLANNER_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("Planner timed out after %ds", PLANNER_TIMEOUT)
        raw = _recover_stdout(exc)
        return PlanResult(raw_output=raw, plan=None)

    raw = result.stdout
    plan = extract_json(raw)
    return PlanResult(raw_output=raw, plan=plan)


def run_coder(
    plan_json: str,
    branch_name: str,
    feedback: str | None = None,
    cwd: str | None = None,
) -> CoderResult:
    """Invoke the Coder agent to implement the plan.

    Uses Popen with a stall detector that kills the process if
    no stdout activity is seen for CODER_STALL_TIMEOUT seconds.
    Raises AgentStalled on stall so the orchestrator can leave
    the branch as-is for human inspection.
    """
    template = load_prompt("coder")
    feedback_section = f"\n\n## Reviewer Feedback\n{feedback}" if feedback else ""
    prompt = (
        template.replace("{plan}", plan_json)
        .replace("{branch_name}", branch_name)
        .replace("{feedback_section}", feedback_section)
    )

    cmd = [
        "claude",
        "--print",
        "-p",
        prompt,
        "--allowedTools",
        "Read",
        "Glob",
        "Grep",
        "Edit",
        "Write",
        "Bash",
        "--max-budget-usd",
        "10",
    ]

    # stdbuf -oL forces line-buffered stdout on the child process.
    # Without this, pipe buffering means our stall detector sees
    # no output even while the agent is actively working.
    raw_out, raw_err, stalled = _run_with_stall_detection(
        ["stdbuf", "-oL", *cmd],
        cwd=cwd,
        hard_timeout=CODER_TIMEOUT,
        stall_timeout=CODER_STALL_TIMEOUT,
    )

    if stalled:
        agent_name = "Coder"
        raise AgentStalledError(
            agent_name,
            CODER_STALL_TIMEOUT,
            partial_stdout=raw_out,
            partial_stderr=raw_err,
        )

    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    branch = branch_result.stdout.strip() or branch_name

    return CoderResult(raw_output=raw_out, branch=branch)


def _run_with_stall_detection(
    cmd: list[str],
    *,
    cwd: str | None,
    hard_timeout: int,
    stall_timeout: int,
) -> tuple[str, str, bool]:
    """Run a subprocess, killing it if stdout goes silent.

    Returns (stdout, stderr, was_stalled).
    """
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    last_activity = time.monotonic()
    stalled = False
    lock = threading.Lock()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )

    def _read_stdout() -> None:
        nonlocal last_activity
        for line in proc.stdout:
            with lock:
                out_chunks.append(line)
                last_activity = time.monotonic()

    def _read_stderr() -> None:
        for line in proc.stderr:
            with lock:
                err_chunks.append(line)

    stdout_reader = threading.Thread(target=_read_stdout, daemon=True)
    stderr_reader = threading.Thread(target=_read_stderr, daemon=True)
    stdout_reader.start()
    stderr_reader.start()

    deadline = time.monotonic() + hard_timeout
    while proc.poll() is None:
        now = time.monotonic()
        if now >= deadline:
            logger.warning("Coder hard timeout after %ds", hard_timeout)
            proc.terminate()
            break
        with lock:
            idle = now - last_activity
        if idle >= stall_timeout:
            logger.warning(
                "Coder stalled — no output for %ds, killing",
                stall_timeout,
            )
            proc.terminate()
            stalled = True
            break
        time.sleep(1)

    stdout_reader.join(timeout=5)
    stderr_reader.join(timeout=5)
    with lock:
        raw_out = "".join(out_chunks)
        raw_err = "".join(err_chunks)
    return raw_out, raw_err, stalled


def run_code_review(diff: str, plan_json: str) -> CodeReviewResult:
    """Invoke the code review agent to analyze the diff against the plan.

    This agent only performs code review — no lint or test analysis.
    Sensor checks are handled programmatically by the orchestrator.
    """
    template = load_prompt("code_review")
    prompt = template.replace("{plan}", plan_json).replace("{diff}", diff)

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--allowedTools",
                "Read",
                "Glob",
                "Grep",
                "--max-budget-usd",
                "5",
            ],
            capture_output=True,
            text=True,
            timeout=CODE_REVIEW_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("Code review timed out after %ds", CODE_REVIEW_TIMEOUT)
        raw = _recover_stdout(exc)
        return CodeReviewResult(raw_output=raw, findings=None)

    raw = result.stdout
    parsed = extract_json(raw)
    findings = parsed.get("findings") if parsed else None
    return CodeReviewResult(raw_output=raw, findings=findings)


def get_changed_files(
    cwd: str,
    base: str = "develop",
) -> list[str]:
    """Get the list of files changed relative to the base branch."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    return [f for f in result.stdout.strip().splitlines() if f.strip()]


def run_lint(
    cwd: str,
    changed_files: list[str] | None = None,
) -> SensorResult:
    """Run ruff check and format on changed files only.

    If changed_files is None or empty, checks the whole directory
    (useful for local dev but not recommended for the pipeline).
    """
    targets = changed_files or ["."]

    check = subprocess.run(
        ["uv", "run", "ruff", "check", *targets],
        capture_output=True,
        text=True,
        timeout=LINT_TIMEOUT,
        cwd=cwd,
        check=False,
    )

    fmt = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", *targets],
        capture_output=True,
        text=True,
        timeout=LINT_TIMEOUT,
        cwd=cwd,
        check=False,
    )

    passed = check.returncode == 0 and fmt.returncode == 0
    check_out = f"=== ruff check ===\n{check.stdout}{check.stderr}"
    fmt_out = f"=== ruff format ===\n{fmt.stdout}{fmt.stderr}"
    return SensorResult(
        passed=passed,
        output=f"{check_out}\n{fmt_out}",
        details={
            "check_rc": check.returncode,
            "format_rc": fmt.returncode,
        },
    )


def get_diff(cwd: str, base: str = "develop") -> str:
    """Get the diff between the current branch and the base branch."""
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    return result.stdout


def push_branch(cwd: str, branch: str) -> None:
    """Push the branch to origin."""
    subprocess.run(
        ["git", "push", "-u", "origin", branch],
        check=True,
        cwd=cwd,
    )


def create_draft_pr(
    repo: str,
    branch: str,
    issue: dict,
    plan: dict,
) -> str:
    """Create a draft PR and return its URL."""
    title = plan.get(
        "issue_title",
        issue.get("title", f"Resolve #{issue['number']}"),
    )
    if len(title) > MAX_PR_TITLE_LENGTH:
        title = title[: MAX_PR_TITLE_LENGTH - 3] + "..."

    body = (
        f"Resolves #{issue['number']}\n\n"
        f"## Plan\n```json\n{json.dumps(plan, indent=2)}\n```"
    )

    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--head",
            branch,
            "--base",
            "develop",
            "--title",
            title,
            "--body",
            body,
            "--draft",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
