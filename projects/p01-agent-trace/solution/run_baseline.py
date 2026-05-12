"""P01 solution — run a baseline prompt and print a structured trace summary.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_baseline.py

Required env vars:  LLM_API_KEY, LLM_MODEL
Optional:           AGENT_SERVER (default http://127.0.0.1:18000)
"""

import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent

PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
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


def print_trace_summary(conversation: RemoteConversation, wall_seconds: float) -> None:
    """Walk the event list and print a structured summary."""
    events = conversation.state.events
    tool_calls: Counter[str] = Counter()
    files_read: list[str] = []
    files_edited: list[str] = []
    compaction_fired = False

    for event in events:
        event_type = getattr(event, "type", None) or type(event).__name__

        # Count tool calls by tool name
        if hasattr(event, "tool") and hasattr(event, "tool_input"):
            tool_calls[event.tool] += 1

        # Track file operations from tool inputs
        if hasattr(event, "tool_input") and isinstance(event.tool_input, dict):
            path = event.tool_input.get("path", "")
            command = event.tool_input.get("command", "")
            if command == "view" and path:
                files_read.append(path)
            elif command in ("str_replace", "create", "insert") and path:
                files_edited.append(path)

        # Detect compaction
        if "compact" in event_type.lower() or "condensed" in event_type.lower():
            compaction_fired = True

    metrics = conversation.conversation_stats.get_combined_metrics()

    print("\n" + "=" * 60)
    print("TRACE SUMMARY")
    print("=" * 60)
    print(f"  Model          : {os.environ.get('LLM_MODEL', '?')}")
    print(f"  Prompt         : {PROMPT[:70]}...")
    print(f"  Total events   : {len(events)}")
    print(f"  Wall-clock     : {wall_seconds:.1f}s")
    print(f"  Cost           : ${metrics.accumulated_cost:.4f}")
    print(f"  Tokens (in)    : {metrics.accumulated_prompt_tokens}")
    print(f"  Tokens (out)   : {metrics.accumulated_completion_tokens}")
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
    model = require_env("LLM_MODEL")
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    agent = get_default_agent(llm=llm, cli_mode=True)

    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=tempfile.mkdtemp(prefix="p01_baseline_"),
    )
    conversation = Conversation(agent=agent, workspace=workspace, visualize=True)
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
