"""P01 solution — run a baseline prompt and print a structured trace summary.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_baseline.py

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent
from _runtime import (
    resolve_api_key,
    resolve_server_working_dir as resolve_working_dir,
    token_counts,
)

PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def tool_event_parts(event) -> tuple[str | None, dict]:
    """Read tool name/arguments across SDK event shape changes."""
    tool = getattr(event, "tool", None) or getattr(event, "tool_name", None)
    args = getattr(event, "tool_input", None)

    tool_call = getattr(event, "tool_call", None)
    if tool_call is not None:
        tool = tool or getattr(tool_call, "name", None)
        args = args or getattr(tool_call, "arguments", None)

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}

    return tool, args


def print_trace_summary(conversation: RemoteConversation, wall_seconds: float) -> None:
    """Walk the event list and print a structured summary."""
    events = conversation.state.events
    tool_calls: Counter[str] = Counter()
    files_read: list[str] = []
    files_edited: list[str] = []
    compaction_fired = False

    for event in events:
        event_type = getattr(event, "type", None) or type(event).__name__
        tool, tool_input = tool_event_parts(event)

        # Count tool calls by tool name
        if tool:
            tool_calls[tool] += 1

        # Track file operations from tool inputs
        if tool_input:
            path = tool_input.get("path", "") or tool_input.get("file_path", "")
            command = tool_input.get("command", "")
            if command == "view" and path:
                files_read.append(path)
            elif command in ("str_replace", "create", "insert") and path:
                files_edited.append(path)

        # Detect compaction
        if "compact" in event_type.lower() or "condensed" in event_type.lower():
            compaction_fired = True

    metrics = conversation.conversation_stats.get_combined_metrics()
    prompt_tokens, completion_tokens = token_counts(metrics)

    print("\n" + "=" * 60)
    print("TRACE SUMMARY")
    print("=" * 60)
    print(f"  Model          : {os.environ.get('LLM_MODEL', DEFAULT_MODEL)}")
    print(f"  Prompt         : {PROMPT[:70]}...")
    print(f"  Total events   : {len(events)}")
    print(f"  Wall-clock     : {wall_seconds:.1f}s")
    print(f"  Cost           : ${metrics.accumulated_cost:.4f}")
    print(f"  Tokens (in)    : {prompt_tokens}")
    print(f"  Tokens (out)   : {completion_tokens}")
    print()
    print("  Tool calls by type:")
    for tool, count in tool_calls.most_common():
        print(f"    {tool:20s} {count}")
    print()
    print(f"  Files read     : {len(files_read)}")
    for f in files_read[:10]:
        print(f"    {f}")
    if len(files_read) > 10:
        print(f"    ... and {len(files_read) - 10} more")
    print(f"  Files edited   : {len(files_edited)}")
    for f in files_edited:
        print(f"    {f}")
    print(f"  Compaction     : {'YES' if compaction_fired else 'no'}")
    print("=" * 60)


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    agent = get_default_agent(llm=llm, cli_mode=True)

    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=resolve_working_dir(),
    )
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(PROMPT)
        conversation.run()
        wall = time.time() - t0

        print_trace_summary(conversation, wall)
    finally:
        conversation.close()


if __name__ == "__main__":
    main()
