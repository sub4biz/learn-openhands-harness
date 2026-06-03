"""P08 solution - compare manual orchestration with dynamic workflows.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_dynamic_workflow.py

Cheap verification:
    uv run python run_dynamic_workflow.py --dry-run

Required env vars for live mode: LLM_API_KEY
Optional: LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
          AGENT_SERVER (default http://127.0.0.1:18000)
          WORKSPACE_DIR (default current directory)
          P08_MAX_ITERATIONS (default 40 per agent run)

Dynamic mode requires an SDK build that exposes openhands.tools.workflow.WorkflowToolSet.
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
When asked to review code with a dynamic workflow:
1. Inspect the target enough to choose review dimensions.
2. Choose 3 to 5 independent reviewer specs. Each spec must include name,
   focus, evidence_required, and likely failure_mode.
3. Use wf.map_agents() to fan out reviewer specs to code_reviewer sub-agents.
4. Use wf.reduce_agent() to synthesize findings with review_synthesizer.
5. Write final artifacts under .harness_workflow/dynamic/.

Hard limits:
- Do not edit the reviewed source file.
- Do not read .env or print secret values.
- Do not make network calls.
- Use at most 5 reviewer sub-agents.
- Require exact file paths and line references for every concrete finding.
- Preserve uncertainty from individual reviewers.

Required artifacts:
- .harness_workflow/dynamic/REVIEW.md
- .harness_workflow/dynamic/WORKFLOW_SUMMARY.md

Workflow API shape:
- await wf.map_agents(items=..., prompt="...", subagent_type="code_reviewer")
- await wf.reduce_agent(items=..., prompt="...", subagent_type="review_synthesizer")
"""

DYNAMIC_PROMPT = """\
Review {target} using a dynamic workflow.

First inspect the file enough to choose the right review dimensions. Then use
the workflow tool to fan out bounded reviewer sub-agents and reduce their
findings into one report.

Write:
- .harness_workflow/dynamic/REVIEW.md
- .harness_workflow/dynamic/WORKFLOW_SUMMARY.md

The summary must list:
- review dimensions chosen
- sub-agent roles used
- evidence checked
- limits hit
- whether a fixed manual workflow would have been simpler

Do not edit source files. Do not make network calls. Do not read .env.
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


def copy_workspace(source: Path, prefix: str) -> Path:
    run_root = Path(
        os.environ.get("P08_RUN_ROOT", source / ".openhands-runs" / "p08-dynamic-workflows")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=prefix, dir=run_root)) / "repo"
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


def run_default_agent_prompt(label: str, llm, server: str, working_dir: Path, prompt: str) -> dict:
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

    return _run_conversation(label, conversation, prompt)


def _run_conversation(label: str, conversation, prompt: str) -> dict:
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


def run_manual(llm, server: str, workspace: Path, target: str) -> tuple[Path, list[dict]]:
    copied_workspace = copy_workspace(workspace, "p08_manual_")
    print(f"\n--- Config A: fixed manual workflow ({copied_workspace}) ---")
    print(f"Agent-server working_dir: {server_visible_path(copied_workspace)}")

    results = []
    for step in MANUAL_REVIEWERS:
        results.append(
            run_default_agent_prompt(
                f"manual:{step.label}",
                llm,
                server,
                copied_workspace,
                step.prompt.format(target=target),
            )
        )
    results.append(
        run_default_agent_prompt("manual:aggregate", llm, server, copied_workspace, MANUAL_AGGREGATE_PROMPT)
    )
    return copied_workspace, results


def build_skill(name: str, content: str):
    try:
        from openhands.sdk.context import Skill

        return Skill(name=name, content=content, trigger=None)
    except Exception:
        return {"name": name, "content": content}


def build_agent_context(agent_context_cls, skills: list, suffix: str):
    try:
        return agent_context_cls(skills=skills, system_message_suffix=suffix)
    except TypeError:
        try:
            return agent_context_cls(skills=skills, system_message=suffix)
        except TypeError:
            return agent_context_cls(skills=skills)


def require_workflow_imports():
    try:
        from openhands.sdk import Agent, Conversation, RemoteConversation, Workspace
        try:
            from openhands.sdk import AgentContext
        except ImportError:
            from openhands.sdk.context import AgentContext
        try:
            from openhands.sdk import Tool
        except ImportError:
            try:
                from openhands.sdk.tool import Tool
            except ImportError:
                from openhands.sdk.tool.spec import Tool
        from openhands.sdk.subagent import register_agent_if_absent
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.terminal import TerminalTool
        from openhands.tools.workflow import WorkflowToolSet
    except Exception as exc:
        print(
            "\n".join(
                [
                    "Dynamic workflow mode requires an OpenHands SDK build with WorkflowToolSet.",
                    "The dry run and manual mode still work.",
                    "Install a workflow-enabled SDK build, then rerun --mode dynamic.",
                    f"Import error: {type(exc).__name__}: {exc}",
                ]
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)

    return {
        "Agent": Agent,
        "AgentContext": AgentContext,
        "Conversation": Conversation,
        "RemoteConversation": RemoteConversation,
        "Workspace": Workspace,
        "Tool": Tool,
        "register_agent_if_absent": register_agent_if_absent,
        "FileEditorTool": FileEditorTool,
        "TerminalTool": TerminalTool,
        "WorkflowToolSet": WorkflowToolSet,
    }


def run_dynamic(llm, server: str, workspace: Path, target: str) -> tuple[Path, list[dict]]:
    imports = require_workflow_imports()
    Agent = imports["Agent"]
    AgentContext = imports["AgentContext"]
    Conversation = imports["Conversation"]
    RemoteConversation = imports["RemoteConversation"]
    Workspace = imports["Workspace"]
    Tool = imports["Tool"]
    register_agent_if_absent = imports["register_agent_if_absent"]
    FileEditorTool = imports["FileEditorTool"]
    TerminalTool = imports["TerminalTool"]
    WorkflowToolSet = imports["WorkflowToolSet"]

    copied_workspace = copy_workspace(workspace, "p08_dynamic_")
    print(f"\n--- Config B: model-authored dynamic workflow ({copied_workspace}) ---")
    print(f"Agent-server working_dir: {server_visible_path(copied_workspace)}")

    def create_code_reviewer(child_llm):
        return Agent(
            llm=child_llm,
            tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)],
            agent_context=build_agent_context(
                AgentContext,
                [build_skill("bounded_code_review", "Review code only. Do not edit. Cite exact paths and lines.")],
                "You are a bounded code reviewer. Do not modify files.",
            ),
        )

    def create_review_synthesizer(child_llm):
        return Agent(
            llm=child_llm,
            tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)],
            agent_context=build_agent_context(
                AgentContext,
                [build_skill("review_synthesis", "Synthesize reviewer findings without inventing unsupported issues.")],
                "You synthesize independent code-review findings. Preserve uncertainty.",
            ),
        )

    register_agent_if_absent("code_reviewer", create_code_reviewer, "Reviews code from a specific perspective")
    register_agent_if_absent("review_synthesizer", create_review_synthesizer, "Synthesizes code review findings")

    parent_agent = Agent(
        llm=llm,
        tools=[Tool(name=WorkflowToolSet.name)],
        agent_context=build_agent_context(
            AgentContext,
            [build_skill("workflow_orchestrator", DYNAMIC_WORKFLOW_SKILL)],
            "Use workflows only when they fit the skill. Keep runs bounded and inspectable.",
        ),
    )
    remote_workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=server_visible_path(copied_workspace),
    )
    conversation = Conversation(
        agent=parent_agent,
        workspace=remote_workspace,
        max_iteration_per_run=resolve_max_iterations(),
    )
    assert isinstance(conversation, RemoteConversation)

    result = _run_conversation(
        "dynamic:workflow",
        conversation,
        DYNAMIC_PROMPT.format(target=target),
    )
    return copied_workspace, [result]


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


def print_report_locations(locations: list[tuple[str, Path]]) -> None:
    print("\nReports:")
    for label, root in locations:
        if label == "manual":
            report = root / ".harness_workflow" / "manual" / "REVIEW.md"
            print(f"- manual:  {report}")
        else:
            report = root / ".harness_workflow" / "dynamic" / "REVIEW.md"
            summary = root / ".harness_workflow" / "dynamic" / "WORKFLOW_SUMMARY.md"
            print(f"- dynamic: {report}")
            print(f"- summary: {summary}")


def print_dry_run(mode: str, workspace: Path, target: str) -> None:
    print(f"Workspace: {workspace}")
    print(f"Target: {target}")
    print(f"Mode: {mode}")
    print("\nNo model calls will be made.")

    if mode in {"both", "manual"}:
        print("\n--- Config A: fixed manual reviewers ---")
        for step in MANUAL_REVIEWERS:
            print(f"\n[{step.label}] -> {step.output}")
            print(textwrap.indent(step.prompt.format(target=target).strip(), "  "))
        print("\n[aggregate] -> .harness_workflow/manual/REVIEW.md")
        print(textwrap.indent(MANUAL_AGGREGATE_PROMPT.strip(), "  "))

    if mode in {"both", "dynamic"}:
        print("\n--- Config B: workflow orchestrator skill ---")
        print(textwrap.indent(DYNAMIC_WORKFLOW_SKILL.strip(), "  "))
        print("\n[dynamic prompt] -> .harness_workflow/dynamic/REVIEW.md")
        print(textwrap.indent(DYNAMIC_PROMPT.format(target=target).strip(), "  "))


def run_live(mode: str, workspace: Path, target: str) -> None:
    from pydantic import SecretStr
    from openhands.sdk import LLM

    api_key, model, server = require_live_env()
    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    all_results: list[dict] = []
    locations: list[tuple[str, Path]] = []

    if mode in {"both", "manual"}:
        manual_workspace, manual_results = run_manual(llm, server, workspace, target)
        locations.append(("manual", manual_workspace))
        all_results.extend(manual_results)

    if mode in {"both", "dynamic"}:
        dynamic_workspace, dynamic_results = run_dynamic(llm, server, workspace, target)
        locations.append(("dynamic", dynamic_workspace))
        all_results.extend(dynamic_results)

    print_results(all_results)
    print_report_locations(locations)
    print("\nCompare orchestration code, trace visibility, and final report quality.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare fixed and dynamic workflow orchestration.")
    parser.add_argument("--mode", choices=["both", "manual", "dynamic"], default="manual")
    parser.add_argument("--workspace", default=None, help="Repo to review. Defaults to WORKSPACE_DIR or cwd.")
    parser.add_argument("--target", default=None, help="Target file inside the workspace.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and validate config without model calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    target = resolve_target(workspace, args.target)
    if args.dry_run:
        print_dry_run(args.mode, workspace, target)
    else:
        run_live(args.mode, workspace, target)


if __name__ == "__main__":
    main()
