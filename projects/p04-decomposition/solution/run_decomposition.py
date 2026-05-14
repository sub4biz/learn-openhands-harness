"""P04 solution - compare monolithic vs. decomposed repo review.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py

Cheap verification:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py --dry-run

Required env vars for live mode: LLM_API_KEY
Optional: LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
          AGENT_SERVER (default http://127.0.0.1:18000)
          WORKSPACE_DIR (default current directory)
          P04_MAX_ITERATIONS (default 60 per agent run)
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
from score_report import parse_score_spec, print_scorecards


DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SERVER = "http://127.0.0.1:18000"
DEFAULT_MAX_ITERATIONS = 60

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

MONOLITH_PROMPT = """\
Review this repository for release readiness.

Produce a file named RELEASE_READINESS.md at the repo root.

Cover these areas:
1. Documentation accuracy: README, quickstart, and project instructions.
2. Setup and test commands: what commands exist, what prerequisites they need, and whether the docs match them.
3. Secret and environment handling: .env.example, .gitignore, API-key instructions, and places where secrets could leak.
4. Safety warnings: whether dockerless/local execution risks are explained clearly.
5. Project structure: numbered project flow, links, starter/solution consistency.
6. Concrete fixes: prioritize findings as P0, P1, or P2.

Rules:
- Do not read .env or print secret values.
- Cite exact file paths for every finding.
- If something is fine, say so briefly.
- Write the final report to RELEASE_READINESS.md.
- Before finalizing, verify that any summary issue counts match the P0/P1/P2
  tables in the report.
- Keep the run bounded: prefer targeted searches and samples over exhaustive
  file-by-file reading.
"""


@dataclass(frozen=True)
class Step:
    label: str
    output: str
    prompt: str


DECOMPOSED_STEPS = [
    Step(
        label="docs",
        output=".harness_review/docs.md",
        prompt="""\
Review documentation accuracy only.

Focus on README.md, 01-quickstart.md, 02-harness-tour.md, and projects/README.md.
Check whether links, project counts, numbering, and setup instructions are internally consistent.

Rules:
- Do not fix files.
- Cite exact file paths.
- Classify findings as P0, P1, or P2.
- Write your scoped report to .harness_review/docs.md.
- Keep this scoped. Use targeted searches and only the files listed above.
""",
    ),
    Step(
        label="setup",
        output=".harness_review/setup.md",
        prompt="""\
Review setup and test commands only.

Focus on scripts/, project starter/solution scripts, quickstart commands, and any dependency assumptions.
Identify commands that are missing, stale, ambiguous, or require prerequisites not stated in the docs.

Rules:
- Do not run destructive commands.
- Do not install packages.
- Cite exact file paths.
- Classify findings as P0, P1, or P2.
- Write your scoped report to .harness_review/setup.md.
- Keep this scoped. Use targeted searches and only inspect files relevant to commands.
""",
    ),
    Step(
        label="safety",
        output=".harness_review/safety.md",
        prompt="""\
Review secret handling and safety warnings only.

Read only these files unless one exact citation must be verified:
- .gitignore
- .env.example
- README.md
- 01-quickstart.md
- 02-harness-tour.md
- projects/README.md
- projects/p06-safety/README.md

Rules:
- Do not read .env or print secret values.
- Do not make network calls.
- Cite exact file paths.
- Classify findings as P0, P1, or P2.
- Write your scoped report to .harness_review/safety.md.
- Keep this scoped. Do not inspect scripts, security policy templates, or
  unrelated project docs.
""",
    ),
    Step(
        label="projects",
        output=".harness_review/projects.md",
        prompt="""\
Review project structure only.

Focus on projects/*/README.md, starter/solution directories, next links, and whether artifacts carry forward coherently.
Check whether numbering and project names are consistent.

Rules:
- Do not fix files.
- Cite exact file paths.
- Classify findings as P0, P1, or P2.
- Write your scoped report to .harness_review/projects.md.
- Keep this scoped. Check structure and links without rereading unrelated prose.
""",
    ),
]

AGGREGATE_PROMPT = """\
Read the scoped review files in .harness_review/:
- docs.md
- setup.md
- safety.md
- projects.md

Produce RELEASE_READINESS.md at the repo root.

The final report must include:
1. Overall release-readiness verdict.
2. P0/P1/P2 table with exact file paths.
3. A short note on which scoped check found each issue.
4. A "No issue found" section for areas that passed.
5. A final prioritized fix list.

Rules:
- Do not read .env or print secret values.
- Preserve uncertainty from the scoped reports.
- Do not invent findings not supported by the scoped reports.
- Before finalizing, verify that any summary issue counts match the P0/P1/P2
  tables in the report.
- Do not run a broad repo review. Read only the scoped reports unless one exact
  cited path needs verification.
"""


def load_dotenv() -> None:
    """Load the nearest repo-level .env without overriding existing env vars."""
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


def copy_workspace(source: Path, prefix: str) -> Path:
    run_root = Path(
        os.environ.get("P04_RUN_ROOT", source / ".openhands-runs" / "p04-decomposition")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=prefix, dir=run_root)) / "repo"
    shutil.copytree(source, destination, ignore=IGNORE_PATTERNS)
    return destination


def print_dry_run(mode: str, workspace: Path) -> None:
    print(f"Workspace: {workspace}")
    print(f"Mode: {mode}")
    print("\nNo model calls will be made.")
    if mode in {"both", "monolith"}:
        print("\n--- monolith prompt ---")
        print(textwrap.indent(MONOLITH_PROMPT.strip(), "  "))
    if mode in {"both", "decomposed"}:
        print("\n--- decomposed prompts ---")
        for step in DECOMPOSED_STEPS:
            print(f"\n[{step.label}] -> {step.output}")
            print(textwrap.indent(step.prompt.strip(), "  "))
        print("\n[aggregate] -> RELEASE_READINESS.md")
        print(textwrap.indent(AGGREGATE_PROMPT.strip(), "  "))


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
    raw = os.environ.get("P04_MAX_ITERATIONS", str(DEFAULT_MAX_ITERATIONS))
    try:
        value = int(raw)
    except ValueError:
        print(f"P04_MAX_ITERATIONS must be an integer, got: {raw}", file=sys.stderr)
        raise SystemExit(2)
    if value < 1:
        print("P04_MAX_ITERATIONS must be at least 1", file=sys.stderr)
        raise SystemExit(2)
    return value


def _event_line(event) -> str:
    event_type = type(event).__name__
    tool = getattr(event, "tool", None) or getattr(event, "tool_name", None)
    summary = getattr(event, "summary", None)
    content = getattr(event, "content", None)
    text = str(summary or tool or content or event).replace("\n", " ")
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return f"- {event_type}: {text}"


def write_truncated_artifact(
    working_dir: Path,
    artifact_name: str,
    label: str,
    exc: Exception,
    conversation,
    wall_seconds: float,
    max_iterations: int,
) -> Path:
    """Persist a readable artifact when an agent run stops before completion."""
    try:
        conversation.state.refresh_from_server()
    except Exception:
        pass

    events = list(conversation.state.events)
    partial_report = working_dir / "RELEASE_READINESS.md"
    artifact = working_dir / artifact_name
    lines = [
        f"# {label} Run Truncated",
        "",
        "This run did not complete. The harness kept this artifact so the",
        "failed monolithic attempt can be compared against the decomposed run",
        "instead of disappearing behind a stack trace.",
        "",
        f"- Max iterations: {max_iterations}",
        f"- Wall time before failure: {wall_seconds:.1f}s",
        f"- Events captured: {len(events)}",
        f"- Exception: `{type(exc).__name__}: {exc}`",
        "",
    ]

    if partial_report.exists():
        lines.extend(
            [
                "## Partial RELEASE_READINESS.md",
                "",
                partial_report.read_text(encoding="utf-8", errors="replace"),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Partial RELEASE_READINESS.md",
                "",
                "The agent did not write `RELEASE_READINESS.md` before stopping.",
                "",
            ]
        )

    lines.extend(["## Recent Events", ""])
    lines.extend(_event_line(event) for event in events[-20:])
    lines.append("")
    artifact.write_text("\n".join(lines), encoding="utf-8")
    return artifact


def run_prompt(
    label: str,
    llm,
    server: str,
    working_dir: Path,
    prompt: str,
    max_iterations: int,
    failure_artifact: str | None = None,
) -> dict:
    from openhands.sdk import Conversation, RemoteConversation, Workspace
    from openhands.sdk.conversation.exceptions import ConversationRunError
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
        max_iteration_per_run=max_iterations,
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(prompt)
        failed = False
        artifact_path = None
        try:
            conversation.run()
        except ConversationRunError as exc:
            if not failure_artifact:
                raise
            failed = True
            wall = time.time() - t0
            artifact_path = write_truncated_artifact(
                working_dir,
                failure_artifact,
                label,
                exc,
                conversation,
                wall,
                max_iterations,
            )
        else:
            wall = time.time() - t0
        metrics = conversation.conversation_stats.get_combined_metrics()
        prompt_tokens, completion_tokens = token_counts(metrics)
        return {
            "label": label,
            "status": "failed" if failed else "ok",
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": float(getattr(metrics, "accumulated_cost", 0.0) or 0.0),
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
            "artifact": artifact_path,
        }
    finally:
        conversation.close()


def write_scoped_failure(working_dir: Path, output: str, label: str, exc: Exception) -> None:
    target = working_dir / output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                f"# {label} Check Failed",
                "",
                "P1: This scoped check did not complete.",
                "",
                f"Exception: `{type(exc).__name__}: {exc}`",
                "",
                "The harness preserved this failure as a scoped artifact so the",
                "aggregate step can report the missing coverage instead of losing",
                "the whole decomposed run.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_live(mode: str, workspace: Path, resume_dir: Path | None) -> None:
    from pydantic import SecretStr
    from openhands.sdk import LLM

    api_key, model, server = require_live_env()
    max_iterations = resolve_max_iterations()
    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    results = []
    report_specs: list[tuple[str, Path]] = []

    if mode in {"both", "monolith"}:
        mono_dir = copy_workspace(workspace, "p04_monolith_")
        print(f"\n--- Config A: monolithic task ({mono_dir}) ---")
        print(f"Agent-server working_dir: {server_visible_path(mono_dir)}")
        result = run_prompt(
            "monolith",
            llm,
            server,
            mono_dir,
            MONOLITH_PROMPT,
            max_iterations,
            failure_artifact="MONOLITH_TRUNCATED.md",
        )
        results.append(result)
        report_path = result["artifact"] or mono_dir / "RELEASE_READINESS.md"
        report_specs.append(("monolith", report_path))

    if mode in {"both", "decomposed"}:
        decomp_dir = resume_dir or copy_workspace(workspace, "p04_decomposed_")
        print(f"\n--- Config B: decomposed task ({decomp_dir}) ---")
        print(f"Agent-server working_dir: {server_visible_path(decomp_dir)}")
        for step in DECOMPOSED_STEPS:
            if resume_dir and (decomp_dir / step.output).exists():
                print(f"Skipping decomposed:{step.label}; {step.output} already exists.")
                continue
            try:
                results.append(
                    run_prompt(
                        f"decomposed:{step.label}",
                        llm,
                        server,
                        decomp_dir,
                        step.prompt,
                        max_iterations,
                    )
                )
            except Exception as exc:
                print(f"decomposed:{step.label} failed: {type(exc).__name__}: {exc}")
                write_scoped_failure(decomp_dir, step.output, step.label, exc)
                results.append(
                    {
                        "label": f"decomposed:{step.label}:failed",
                        "status": "failed",
                        "events": 0,
                        "wall": 0.0,
                        "cost": 0.0,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "artifact": decomp_dir / step.output,
                    }
                )
        results.append(
            run_prompt(
                "decomposed:aggregate",
                llm,
                server,
                decomp_dir,
                AGGREGATE_PROMPT,
                max_iterations,
            )
        )
        report_specs.append(("decomposed", decomp_dir / "RELEASE_READINESS.md"))

    print("\n" + "=" * 96)
    print(
        f"{'Step':<24} {'Status':>8} {'Events':>7} {'Wall':>8} "
        f"{'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}"
    )
    print("-" * 96)
    for row in results:
        print(
            f"{row['label']:<24} {row.get('status', 'ok'):>8} "
            f"{row['events']:>7} {row['wall']:>7.1f}s "
            f"${row['cost']:>9.4f} {row['tokens_in']:>12} {row['tokens_out']:>12}"
        )
        if row.get("artifact"):
            print(f"{'':<24} {'artifact':>8} {row['artifact']}")
    print("=" * 96)
    print_scorecards(report_specs)
    print("\nCompare RELEASE_READINESS.md in each copied workspace.")
    print("The decomposed run should show whether scoped checks improved coverage enough to justify extra calls.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare monolithic and decomposed harness workflows.")
    parser.add_argument("--mode", choices=["both", "monolith", "decomposed"], default="both")
    parser.add_argument("--workspace", default=None, help="Repo to review. Defaults to WORKSPACE_DIR or cwd.")
    parser.add_argument(
        "--score-report",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Score an existing RELEASE_READINESS.md without model calls. May be repeated.",
    )
    parser.add_argument(
        "--resume-dir",
        default=None,
        help="Existing copied workspace for resuming a decomposed run.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and validate config without model calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.score_report:
        print_scorecards([parse_score_spec(spec) for spec in args.score_report])
        return

    workspace = resolve_workspace(args.workspace)
    resume_dir = resolve_workspace(args.resume_dir) if args.resume_dir else None
    if resume_dir and args.mode != "decomposed":
        print("--resume-dir is only supported with --mode decomposed", file=sys.stderr)
        raise SystemExit(2)
    if args.dry_run:
        print_dry_run(args.mode, workspace)
    else:
        run_live(args.mode, workspace, resume_dir)


if __name__ == "__main__":
    main()
