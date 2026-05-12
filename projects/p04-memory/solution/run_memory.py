"""P04 solution — compare no-memory vs. AGENTS.md runs.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_memory.py

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent

PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"

AGENTS_MD = Path(__file__).parent / "AGENTS.md"
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def resolve_api_key() -> str | None:
    key = os.environ.get("AGENT_SERVER_API_KEY")
    if key:
        return key
    path = Path.home() / ".openhands" / "agent-canvas" / "session-api-key.txt"
    return path.read_text().strip() if path.exists() else None


def resolve_working_dir() -> str:
    path = Path(os.environ.get("WORKSPACE_DIR", Path.cwd())).expanduser().resolve()
    if not path.exists():
        print(f"WORKSPACE_DIR does not exist: {path}", file=sys.stderr)
        raise SystemExit(2)
    return str(path)


def copy_workspace(source: str, prefix: str) -> str:
    destination = Path(tempfile.mkdtemp(prefix=prefix)) / "repo"
    shutil.copytree(source, destination, ignore=IGNORE_PATTERNS)
    return str(destination)


def run_config(label: str, llm: LLM, server: str, working_dir: str) -> dict:
    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=working_dir,
    )
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(PROMPT)
        conversation.run()
        wall = time.time() - t0

        metrics = conversation.conversation_stats.get_combined_metrics()
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": metrics.accumulated_cost,
            "tokens_in": metrics.accumulated_prompt_tokens,
        }
    finally:
        conversation.close()


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    source_dir = resolve_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    # --- Config A: no AGENTS.md ---
    dir_no_memory = copy_workspace(source_dir, "p04_no_memory_")
    Path(dir_no_memory, "AGENTS.md").unlink(missing_ok=True)

    # --- Config B: with AGENTS.md ---
    dir_with_memory = copy_workspace(source_dir, "p04_with_memory_")
    if AGENTS_MD.exists():
        shutil.copy(AGENTS_MD, Path(dir_with_memory) / "AGENTS.md")
    else:
        print(f"Warning: {AGENTS_MD} not found, writing a minimal placeholder", file=sys.stderr)
        (Path(dir_with_memory) / "AGENTS.md").write_text(
            "# Agent Notes\n\nThis is agent-canvas, a TypeScript/React UI for OpenHands.\n"
            "Source is in src/. Dev scripts are in the repo root.\n"
        )

    results = []

    print("\n--- Config A: no AGENTS.md ---")
    results.append(run_config("no-memory", llm, server, dir_no_memory))

    print("\n--- Config B: with AGENTS.md ---")
    results.append(run_config("with-memory", llm, server, dir_with_memory))

    print("\n" + "=" * 70)
    print(f"{'Config':<15} {'Events':>7} {'Wall':>8} {'Cost':>10} {'Tokens in':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['label']:<15} {r['events']:>7} {r['wall']:>7.1f}s ${r['cost']:>9.4f} {r['tokens_in']:>12}")
    print("=" * 70)
    print("\nCompare: did the AGENTS.md run skip re-discovery steps?")
    print("Check your traces for compaction events and what they preserved.")


if __name__ == "__main__":
    main()
