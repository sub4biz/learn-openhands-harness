"""P05 solution — compare no-memory vs. AGENTS.md runs.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_memory.py

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent
from _runtime import (
    resolve_api_key,
    resolve_host_working_dir,
    server_visible_path,
    token_counts,
)

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
    ".openhands-runs",
)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def copy_workspace(source: Path, prefix: str) -> Path:
    run_root = Path(
        os.environ.get("P05_RUN_ROOT", source / ".openhands-runs" / "p05-memory")
    ).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=prefix, dir=run_root)) / "repo"
    shutil.copytree(source, destination, ignore=IGNORE_PATTERNS)
    return destination


def to_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return str(value)


def write_trace(label: str, working_dir: Path, conversation, metrics) -> Path:
    prompt_tokens, completion_tokens = token_counts(metrics)
    trace_path = working_dir.parent / f"{label}-events.json"
    payload = {
        "label": label,
        "prompt": PROMPT,
        "metrics": {
            "cost": float(getattr(metrics, "accumulated_cost", 0.0) or 0.0),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "events": [to_jsonable(event) for event in conversation.state.events],
    }
    trace_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return trace_path


def run_config(label: str, llm: LLM, server: str, working_dir: Path) -> dict:
    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=server_visible_path(working_dir),
    )
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(PROMPT)
        conversation.run()
        wall = time.time() - t0

        metrics = conversation.conversation_stats.get_combined_metrics()
        prompt_tokens, _ = token_counts(metrics)
        trace_path = write_trace(label, working_dir, conversation, metrics)
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": metrics.accumulated_cost,
            "tokens_in": prompt_tokens,
            "trace": trace_path,
        }
    finally:
        conversation.close()


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    source_dir = resolve_host_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    # --- Config A: no AGENTS.md ---
    dir_no_memory = copy_workspace(source_dir, "p05_no_memory_")
    (dir_no_memory / "AGENTS.md").unlink(missing_ok=True)

    # --- Config B: with AGENTS.md ---
    dir_with_memory = copy_workspace(source_dir, "p05_with_memory_")
    if AGENTS_MD.exists():
        shutil.copy(AGENTS_MD, dir_with_memory / "AGENTS.md")
    else:
        print(f"Warning: {AGENTS_MD} not found, writing a minimal placeholder", file=sys.stderr)
        (dir_with_memory / "AGENTS.md").write_text(
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
    for r in results:
        print(f"trace {r['label']}: {r['trace']}")
    print("\nCompare: did the AGENTS.md run skip re-discovery steps?")
    print("Run compare_traces.py on the two saved trace paths printed above.")
    print("Check your traces for compaction events and what they preserved.")


if __name__ == "__main__":
    main()
