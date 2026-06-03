"""P08 starter - compare manual orchestration with dynamic workflows.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_dynamic_workflow.py

Cheap verification:
    uv run python run_dynamic_workflow.py --dry-run

Optional env vars:
    P08_MAX_ITERATIONS (default 40 per agent run)

TODO:
    1. Replace DYNAMIC_WORKFLOW_SKILL with a real workflow skill.
    2. Register bounded reviewer and synthesizer sub-agents.
    3. Create a parent agent with WorkflowToolSet.
    4. Ask the model to write the fan-out/fan-in workflow.
    5. Compare orchestration code, trace visibility, cost, and report quality.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from _runtime import (
    resolve_api_key,
    resolve_host_working_dir,
    server_visible_path,
    token_counts,
)


DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SERVER = "http://127.0.0.1:18000"
DEFAULT_MAX_ITERATIONS = 40

IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".openhands-runs",
    ".env",
    ".DS_Store",
)


@dataclass(frozen=True)
class Step:
    label: str
    output: str
    focus: str
    prompt: str


MANUAL_REVIEWERS = [
    Step(
        label="security",
        output=".harness_workflow/manual/security.md",
        focus="security and secret-handling risks",
        prompt="""\
Review {target} for security and secret-handling risks.

Rules:
- Do not edit files.
- Do not read .env or print secret values.
- Cite exact file paths and line numbers.
- Write only your scoped findings to .harness_workflow/manual/security.md.
""",
    ),
    Step(
        label="reliability",
        output=".harness_workflow/manual/reliability.md",
        focus="runtime failures and edge cases",
        prompt="""\
Review {target} for runtime failures, bad error handling, and edge cases.

Rules:
- Do not edit files.
- Cite exact file paths and line numbers.
- Prefer concrete failure modes over style preferences.
- Write only your scoped findings to .harness_workflow/manual/reliability.md.
""",
    ),
    Step(
        label="maintainability",
        output=".harness_workflow/manual/maintainability.md",
        focus="maintainability and API clarity",
        prompt="""\
Review {target} for maintainability, naming clarity, API boundaries, and code organization.

Rules:
- Do not edit files.
- Cite exact file paths and line numbers.
- Separate real maintainability risks from harmless preferences.
- Write only your scoped findings to .harness_workflow/manual/maintainability.md.
""",
    ),
    Step(
        label="tests",
        output=".harness_workflow/manual/tests.md",
        focus="missing tests and verification gaps",
        prompt="""\
Review {target} for missing tests and verification gaps.

Rules:
- Do not edit files.
- Cite exact file paths and line numbers.
- Suggest specific tests only where behavior is visible from the code.
- Write only your scoped findings to .harness_workflow/manual/tests.md.
""",
    ),
]

MANUAL_AGGREGATE_PROMPT = """\
Read these scoped review files:
- .harness_workflow/manual/security.md
- .harness_workflow/manual/reliability.md
- .harness_workflow/manual/maintainability.md
- .harness_workflow/manual/tests.md

Write .harness_workflow/manual/REVIEW.md.

The final report must include:
1. Overall verdict.
2. Prioritized findings with exact paths and line numbers.
3. Which reviewer found each issue.
4. Explicit "No issue found" notes for clean categories.
5. A short note on whether the fixed manual workflow was a good fit.

Rules:
- Do not invent findings beyond the scoped review files.
- Preserve uncertainty from the scoped reviews.
- Do not edit source files.
"""

DYNAMIC_WORKFLOW_SKILL = """\
TODO: Write a skill that tells the model:
- when a dynamic workflow is appropriate
- how many reviewers it may spawn
- which actions are forbidden
- what report and workflow-summary artifacts must be written
- how to preserve evidence and uncertainty
"""

DYNAMIC_PROMPT = """\
TODO: Create a parent agent with the workflow tool and ask it to review {target}.

The model should choose review dimensions dynamically, fan out to bounded
reviewer sub-agents, then reduce the findings into:
- .harness_workflow/dynamic/REVIEW.md
- .harness_workflow/dynamic/WORKFLOW_SUMMARY.md
"""


def load_dotenv() -> None:
    for root in [Path.cwd(), *Path.cwd().parents]:
        env_path = root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
            return


def resolve_workspace(value: str | None) -> Path:
    return resolve_host_working_dir(value)


def _ignored(path: Path) -> bool:
    return any(part in {".git", ".venv", "node_modules", ".openhands-runs"} for part in path.parts)


def resolve_target(workspace: Path, value: str | None) -> str:
    if value:
        raw = Path(value).expanduser()
        candidate = raw if raw.is_absolute() else workspace / raw
        candidate = candidate.resolve()
        try:
            relative = candidate.relative_to(workspace)
        except ValueError:
            print(f"Target must be inside workspace: {candidate}", file=sys.stderr)
            raise SystemExit(2)
        if not candidate.exists() or not candidate.is_file():
            print(f"Target file does not exist: {candidate}", file=sys.stderr)
            raise SystemExit(2)
        return relative.as_posix()

    preferred = [workspace / "projects" / "_runtime.py", workspace / "scripts" / "quickstart.py"]
    for candidate in preferred:
        if candidate.exists():
            return candidate.relative_to(workspace).as_posix()

    for candidate in sorted(workspace.rglob("*.py")):
        if not _ignored(candidate.relative_to(workspace)):
            return candidate.relative_to(workspace).as_posix()

    print("No Python target found. Pass --target path/to/file.py.", file=sys.stderr)
    raise SystemExit(2)


def copy_workspace(source: Path) -> Path:
    run_root = Path(
        os.environ.get("P08_RUN_ROOT", source / ".openhands-runs" / "p08-dynamic-workflows")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="p08_manual_", dir=run_root)) / "repo"
    shutil.copytree(source, destination, ignore=IGNORE_PATTERNS)
    return destination


def require_live_env() -> tuple[str, str, str]:
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Missing required environment variable: LLM_API_KEY", file=sys.stderr)
        raise SystemExit(2)
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", DEFAULT_SERVER)
    return api_key, model, server


def resolve_max_iterations() -> int:
    raw = os.environ.get("P08_MAX_ITERATIONS", str(DEFAULT_MAX_ITERATIONS))
    try:
        value = int(raw)
    except ValueError:
        print(f"P08_MAX_ITERATIONS must be an integer, got: {raw}", file=sys.stderr)
        raise SystemExit(2)
    if value < 1:
        print("P08_MAX_ITERATIONS must be at least 1", file=sys.stderr)
        raise SystemExit(2)
    return value


def run_prompt(label: str, llm, server: str, working_dir: Path, prompt: str) -> dict:
    from openhands.sdk import Conversation, RemoteConversation, Workspace
    from openhands.tools.preset.default import get_default_agent

    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=server_visible_path(working_dir),
    )
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        max_iteration_per_run=resolve_max_iterations(),
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall = time.time() - t0
        metrics = conversation.conversation_stats.get_combined_metrics()
        prompt_tokens, completion_tokens = token_counts(metrics)
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": float(getattr(metrics, "accumulated_cost", 0.0) or 0.0),
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
        }
    finally:
        conversation.close()


def run_manual(workspace: Path, target: str) -> None:
    from pydantic import SecretStr
    from openhands.sdk import LLM

    api_key, model, server = require_live_env()
    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    copied_workspace = copy_workspace(workspace)
    print(f"Manual workflow copied workspace: {copied_workspace}")
    print(f"Agent-server working_dir: {server_visible_path(copied_workspace)}")

    results = []
    for step in MANUAL_REVIEWERS:
        results.append(
            run_prompt(
                f"manual:{step.label}",
                llm,
                server,
                copied_workspace,
                step.prompt.format(target=target),
            )
        )
    results.append(
        run_prompt("manual:aggregate", llm, server, copied_workspace, MANUAL_AGGREGATE_PROMPT)
    )

    print_results(results)
    print(f"Manual report: {copied_workspace / '.harness_workflow' / 'manual' / 'REVIEW.md'}")


def print_results(results: list[dict]) -> None:
    print("\n" + "=" * 96)
    print(
        f"{'Step':<24} {'Events':>7} {'Wall':>8} "
        f"{'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}"
    )
    print("-" * 96)
    for row in results:
        print(
            f"{row['label']:<24} {row['events']:>7} {row['wall']:>7.1f}s "
            f"${row['cost']:>9.4f} {row['tokens_in']:>12} {row['tokens_out']:>12}"
        )
    print("=" * 96)


def print_dry_run(mode: str, workspace: Path, target: str) -> None:
    print(f"Workspace: {workspace}")
    print(f"Target: {target}")
    print(f"Mode: {mode}")
    print("\nNo model calls will be made.")

    if mode in {"both", "manual"}:
        print("\n--- manual fixed reviewers ---")
        for step in MANUAL_REVIEWERS:
            print(f"\n[{step.label}] -> {step.output}")
            print(textwrap.indent(step.prompt.format(target=target).strip(), "  "))
        print("\n[aggregate] -> .harness_workflow/manual/REVIEW.md")
        print(textwrap.indent(MANUAL_AGGREGATE_PROMPT.strip(), "  "))

    if mode in {"both", "dynamic"}:
        print("\n--- dynamic workflow TODO ---")
        print(textwrap.indent(DYNAMIC_WORKFLOW_SKILL.strip(), "  "))
        print("\n--- dynamic prompt TODO ---")
        print(textwrap.indent(DYNAMIC_PROMPT.format(target=target).strip(), "  "))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P08 dynamic workflow starter.")
    parser.add_argument("--mode", choices=["both", "manual", "dynamic"], default="manual")
    parser.add_argument("--workspace", default=None, help="Repo to review. Defaults to WORKSPACE_DIR or cwd.")
    parser.add_argument("--target", default=None, help="Target file inside the workspace.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without model calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    target = resolve_target(workspace, args.target)
    if args.dry_run:
        print_dry_run(args.mode, workspace, target)
        return
    if args.mode in {"both", "dynamic"}:
        print("Dynamic mode is intentionally left as a starter TODO.", file=sys.stderr)
        raise SystemExit(2)
    run_manual(workspace, target)


if __name__ == "__main__":
    main()
