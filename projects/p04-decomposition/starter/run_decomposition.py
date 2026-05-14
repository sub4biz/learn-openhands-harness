"""P04 starter - run one large repo-review task, then add decomposition.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py

Cheap verification:
    uv run --with openhands-sdk --with openhands-tools python run_decomposition.py --dry-run

Optional env vars:
    P04_MAX_ITERATIONS (default 60 per agent run)

TODO:
    1. Add scoped prompts for docs, setup, safety, and project structure.
    2. Run each scoped prompt on the same copied workspace.
    3. Add a final aggregation prompt that reads the scoped reports.
    4. Score both reports against an expected-findings rubric.
    5. Compare whether the monolithic report completed but missed blockers.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import textwrap
import time
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from _runtime import resolve_api_key, resolve_host_working_dir, server_visible_path


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


def copy_workspace(source: Path) -> Path:
    run_root = Path(
        os.environ.get("P04_RUN_ROOT", source / ".openhands-runs" / "p04-decomposition")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="p04_monolith_", dir=run_root)) / "repo"
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
    exc: Exception,
    conversation,
    wall_seconds: float,
    max_iterations: int,
) -> Path:
    try:
        conversation.state.refresh_from_server()
    except Exception:
        pass

    events = list(conversation.state.events)
    partial_report = working_dir / "RELEASE_READINESS.md"
    artifact = working_dir / "MONOLITH_TRUNCATED.md"
    lines = [
        "# Monolith Run Truncated",
        "",
        "This run did not complete. The harness kept this artifact so the",
        "failed monolithic attempt can be compared against a decomposed run",
        "instead of disappearing behind a stack trace.",
        "",
        f"- Max iterations: {max_iterations}",
        f"- Wall time before failure: {wall_seconds:.1f}s",
        f"- Events captured: {len(events)}",
        f"- Exception: `{type(exc).__name__}: {exc}`",
        "",
        "## Partial RELEASE_READINESS.md",
        "",
    ]
    if partial_report.exists():
        lines.append(partial_report.read_text(encoding="utf-8", errors="replace"))
    else:
        lines.append("The agent did not write `RELEASE_READINESS.md` before stopping.")
    lines.extend(["", "## Recent Events", ""])
    lines.extend(_event_line(event) for event in events[-20:])
    lines.append("")
    artifact.write_text("\n".join(lines), encoding="utf-8")
    return artifact


def run_prompt(llm, server: str, working_dir: Path, prompt: str) -> dict:
    from openhands.sdk import Conversation, RemoteConversation, Workspace
    from openhands.sdk.conversation.exceptions import ConversationRunError
    from openhands.tools.preset.default import get_default_agent

    max_iterations = resolve_max_iterations()
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
        artifact = None
        try:
            conversation.run()
        except ConversationRunError as exc:
            failed = True
            wall = time.time() - t0
            artifact = write_truncated_artifact(
                working_dir,
                exc,
                conversation,
                wall,
                max_iterations,
            )
        else:
            wall = time.time() - t0
        metrics = conversation.conversation_stats.get_combined_metrics()
        return {
            "status": "failed" if failed else "ok",
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": float(getattr(metrics, "accumulated_cost", 0.0) or 0.0),
            "artifact": artifact,
        }
    finally:
        conversation.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="P04 starter monolithic repo review.")
    parser.add_argument("--workspace", default=None, help="Repo to review. Defaults to WORKSPACE_DIR or cwd.")
    parser.add_argument("--dry-run", action="store_true", help="Print the prompt without model calls.")
    args = parser.parse_args()

    workspace = resolve_workspace(args.workspace)
    if args.dry_run:
        print(f"Workspace: {workspace}")
        print("\n--- monolith prompt ---")
        print(textwrap.indent(MONOLITH_PROMPT.strip(), "  "))
        print("\nTODO: add decomposed scoped prompts and an aggregation step.")
        return

    from pydantic import SecretStr
    from openhands.sdk import LLM

    api_key, model, server = require_live_env()
    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    copied_workspace = copy_workspace(workspace)
    print(f"Running monolithic repo review in copied workspace: {copied_workspace}")
    print(f"Agent-server working_dir: {server_visible_path(copied_workspace)}")
    result = run_prompt(llm, server, copied_workspace, MONOLITH_PROMPT)
    print(
        f"monolith status={result['status']} events={result['events']} "
        f"wall={result['wall']:.1f}s "
        f"cost=${result['cost']:.4f}"
    )
    if result["artifact"]:
        print(f"truncated artifact: {result['artifact']}")
    print("Next: split the task into scoped checks and compare the final reports.")


if __name__ == "__main__":
    main()
