"""P04 solution - compare monolithic vs. decomposed repo review.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py

Cheap verification:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py --dry-run

Required env vars for live mode: LLM_API_KEY
Optional: LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
          AGENT_SERVER (default http://127.0.0.1:18000)
          WORKSPACE_DIR (default current directory)
          P04_MAX_ITERATIONS (default 24 per agent run)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SERVER = "http://127.0.0.1:18000"

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


@dataclass(frozen=True)
class RubricItem:
    id: str
    priority: str
    title: str
    patterns: tuple[str, ...]


RUBRIC_ITEMS = [
    RubricItem(
        id="agent_canvas_prereq",
        priority="P0",
        title="Identifies agent-canvas as a required external repo/prerequisite",
        patterns=(
            r"agent-canvas.{0,180}(missing|not listed|not stated|undocumented|required external|prerequisite)",
            r"(missing|not listed|not stated|undocumented|required external).{0,180}agent-canvas",
        ),
    ),
    RubricItem(
        id="agent_server_running",
        priority="P0",
        title="Identifies that SDK scripts require a running agent server",
        patterns=(
            r"(agent server|agent-server).{0,180}(must be running|undocumented|connection refused|already running|server dependency)",
            r"(must be running|connection refused|undocumented).{0,180}(agent server|agent-server)",
        ),
    ),
    RubricItem(
        id="api_key_validation",
        priority="P0",
        title="Identifies weak or late LLM_API_KEY validation",
        patterns=(
            r"(llm_api_key|api key).{0,180}(validation|empty|not set|too late|missing)",
            r"(validation|empty|not set|too late|missing).{0,180}(llm_api_key|api key)",
        ),
    ),
    RubricItem(
        id="docker_requirement",
        priority="P0",
        title="Identifies Docker/P06-P07 requirement or dockerless risk clarity",
        patterns=(
            r"docker.{0,180}(required|hidden|buried|p06-p07|p06.*p07|real work)",
            r"(required|hidden|buried|p06-p07|p06.*p07|real work).{0,180}docker",
        ),
    ),
    RubricItem(
        id="correct_release_verdict",
        priority="P0",
        title="Gives a not-ready/do-not-release verdict when blockers are present",
        patterns=(r"not ready|do not release|not release publicly|not ready for public release",),
    ),
    RubricItem(
        id="safety_warning_prominence",
        priority="P1",
        title="Checks prominence of dockerless safety warnings",
        patterns=(
            r"(safety|dockerless|danger).{0,180}(warning|prominent|earlier|banner|placement)",
            r"(warning|prominent|earlier|banner|placement).{0,180}(safety|dockerless|danger)",
        ),
    ),
    RubricItem(
        id="project_title_consistency",
        priority="P1",
        title="Checks project title/name/capitalization consistency",
        patterns=(
            r"(title|project names|capitalization).{0,180}(inconsistent|consistency)",
            r"(inconsistent|consistency).{0,180}(title|project names|capitalization)",
        ),
    ),
    RubricItem(
        id="workspace_dir_default",
        priority="P1",
        title="Checks ambiguous WORKSPACE_DIR/default working directory behavior",
        patterns=(
            r"(workspace_dir|working directory).{0,180}(default|ambiguous|explicit)",
            r"(default|ambiguous|explicit).{0,180}(workspace_dir|working directory)",
        ),
    ),
    RubricItem(
        id="dependency_clarity",
        priority="P1",
        title="Checks per-project package/dependency clarity",
        patterns=(
            r"(dependencies|package|--with).{0,180}(unclear|ambiguous|document)",
            r"(unclear|ambiguous|document).{0,180}(dependencies|package|--with)",
        ),
    ),
]


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
    raw = value or os.environ.get("WORKSPACE_DIR") or "."
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        print(f"Workspace does not exist: {path}", file=sys.stderr)
        raise SystemExit(2)
    if not path.is_dir():
        print(f"Workspace is not a directory: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path


def resolve_server_api_key() -> str | None:
    key = os.environ.get("AGENT_SERVER_API_KEY")
    if key:
        return key
    path = Path.home() / ".openhands" / "agent-canvas" / "session-api-key.txt"
    return path.read_text().strip() if path.exists() else None


def copy_workspace(source: Path, prefix: str) -> Path:
    run_root = Path(
        os.environ.get("P04_RUN_ROOT", source / ".openhands-runs" / "p04-decomposition")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=prefix, dir=run_root)) / "repo"
    shutil.copytree(source, destination, ignore=IGNORE_PATTERNS)
    return destination


def server_visible_path(path: Path) -> str:
    host_root_raw = os.environ.get("AGENT_WORKSPACE_HOST_ROOT") or os.environ.get("PROJECT_PATH")
    server_root_raw = os.environ.get("AGENT_WORKSPACE_SERVER_ROOT")
    if host_root_raw and not server_root_raw:
        server_root_raw = "/projects"
    if not host_root_raw or not server_root_raw:
        return str(path)

    host_root = Path(host_root_raw).expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(host_root)
    except ValueError:
        return str(resolved)
    return str(PurePosixPath(server_root_raw) / PurePosixPath(relative.as_posix()))


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


def parse_score_spec(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        label, _, raw_path = spec.partition("=")
        return label.strip() or Path(raw_path).stem, Path(raw_path).expanduser()
    path = Path(spec).expanduser()
    return path.parent.name or path.stem, path


def matches_rubric_item(text: str, item: RubricItem) -> bool:
    return any(re.search(pattern, text, flags=re.DOTALL) for pattern in item.patterns)


def declared_p0_count(text: str) -> int | None:
    head = text[:2500].lower()
    if "no critical blockers (p0)" in head or "no p0" in head:
        return 0
    patterns = [
        r"(\d+)\s+critical\s+\(p0\)",
        r"(\d+)\s+p0\s+(?:issues|blockers|findings)",
    ]
    for pattern in patterns:
        match = re.search(pattern, head)
        if match:
            return int(match.group(1))
    return None


def p0_table_count(text: str) -> int:
    return len(re.findall(r"^\|\s*P0-\d+\s*\|", text, flags=re.MULTILINE))


def score_report(report_path: Path) -> dict:
    if not report_path.exists():
        return {
            "path": report_path,
            "error": f"Report does not exist: {report_path}",
        }
    text = report_path.read_text(encoding="utf-8")
    lowered = text.lower()
    hits = [item for item in RUBRIC_ITEMS if matches_rubric_item(lowered, item)]
    misses = [item for item in RUBRIC_ITEMS if item not in hits]
    declared = declared_p0_count(text)
    table_count = p0_table_count(text)
    count_ok = declared is None or declared == table_count
    return {
        "path": report_path,
        "hits": hits,
        "misses": misses,
        "declared_p0": declared,
        "table_p0": table_count,
        "count_ok": count_ok,
        "line_count": len(text.splitlines()),
    }


def print_scorecards(specs: list[tuple[str, Path]]) -> None:
    if not specs:
        return
    print("\n" + "=" * 92)
    print("Rubric scorecard")
    print("-" * 92)
    print(
        f"{'Report':<24} {'Coverage':>10} {'P0 rows':>8} "
        f"{'Declared P0':>12} {'Count OK':>9} {'Lines':>7}"
    )
    print("-" * 92)
    scored = []
    for label, path in specs:
        result = score_report(path)
        scored.append((label, result))
        if "error" in result:
            print(f"{label:<24} ERROR: {result['error']}")
            continue
        declared = "n/a" if result["declared_p0"] is None else str(result["declared_p0"])
        print(
            f"{label:<24} {len(result['hits']):>3}/{len(RUBRIC_ITEMS):<6} "
            f"{result['table_p0']:>8} {declared:>12} "
            f"{'yes' if result['count_ok'] else 'no':>9} {result['line_count']:>7}"
        )

    print("\nMissed rubric items:")
    for label, result in scored:
        if "error" in result:
            continue
        if not result["misses"] and result["count_ok"]:
            print(f"- {label}: none")
            continue
        for item in result["misses"]:
            print(f"- {label}: MISS {item.priority} {item.id} - {item.title}")
        if not result["count_ok"]:
            print(
                f"- {label}: FAIL report_count_consistency - declared "
                f"{result['declared_p0']} P0 issues but table lists {result['table_p0']}"
            )
    print("=" * 92)


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
    raw = os.environ.get("P04_MAX_ITERATIONS", "24")
    try:
        value = int(raw)
    except ValueError:
        print(f"P04_MAX_ITERATIONS must be an integer, got: {raw}", file=sys.stderr)
        raise SystemExit(2)
    if value < 1:
        print("P04_MAX_ITERATIONS must be at least 1", file=sys.stderr)
        raise SystemExit(2)
    return value


def run_prompt(
    label: str,
    llm,
    server: str,
    working_dir: Path,
    prompt: str,
    max_iterations: int,
) -> dict:
    from openhands.sdk import Conversation, RemoteConversation, Workspace
    from openhands.tools.preset.default import get_default_agent

    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_server_api_key(),
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
        conversation.run()
        wall = time.time() - t0
        metrics = conversation.conversation_stats.get_combined_metrics()
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": float(getattr(metrics, "accumulated_cost", 0.0) or 0.0),
            "tokens_in": int(getattr(metrics, "accumulated_prompt_tokens", 0) or 0),
            "tokens_out": int(getattr(metrics, "accumulated_completion_tokens", 0) or 0),
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
        results.append(
            run_prompt("monolith", llm, server, mono_dir, MONOLITH_PROMPT, max_iterations)
        )
        report_specs.append(("monolith", mono_dir / "RELEASE_READINESS.md"))

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
                        "events": 0,
                        "wall": 0.0,
                        "cost": 0.0,
                        "tokens_in": 0,
                        "tokens_out": 0,
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

    print("\n" + "=" * 86)
    print(f"{'Step':<24} {'Events':>7} {'Wall':>8} {'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}")
    print("-" * 86)
    for row in results:
        print(
            f"{row['label']:<24} {row['events']:>7} {row['wall']:>7.1f}s "
            f"${row['cost']:>9.4f} {row['tokens_in']:>12} {row['tokens_out']:>12}"
        )
    print("=" * 86)
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
