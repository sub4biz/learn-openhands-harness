"""P01 starter — run a baseline prompt and print event count + cost.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_baseline.py

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import os
import sys
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent

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
        conversation.send_message(PROMPT)
        conversation.run()

        # TODO: inspect conversation.state.events to build a structured trace
        # summary. Count tool calls by type, list files read, check whether
        # compaction fired. The solution shows one way to do this.

        print(f"events: {len(conversation.state.events)}")
        print(f"cost  : {conversation.conversation_stats.get_combined_metrics().accumulated_cost}")
    finally:
        conversation.close()


if __name__ == "__main__":
    main()
