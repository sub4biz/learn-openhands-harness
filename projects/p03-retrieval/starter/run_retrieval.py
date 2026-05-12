"""P03 starter — run with lexical tools only. Add MCP semantic search.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_retrieval.py

Required env vars:  LLM_API_KEY, LLM_MODEL
Optional:           AGENT_SERVER (default http://127.0.0.1:18000)
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Agent, Conversation, RemoteConversation, Workspace
from openhands.sdk.tool import Tool
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool

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


def run_config(label: str, agent: Agent, server: str) -> dict:
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=tempfile.mkdtemp(prefix=f"p03_{label}_"),
    )
    conversation = Conversation(agent=agent, workspace=workspace, visualize=True)
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
        }
    finally:
        conversation.close()


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = require_env("LLM_MODEL")
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    # --- Config A: lexical only ---
    lexical_tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ]
    agent_lexical = Agent(llm=llm, tools=lexical_tools)

    # TODO: Config B — add an MCP semantic-search tool.
    # See https://docs.openhands.dev/sdk/guides/mcp for how to wire MCP servers.
    # agent_semantic = Agent(llm=llm, tools=[...lexical_tools, mcp_search_tool...])

    results = []

    print("\n--- Config A: lexical only ---")
    results.append(run_config("lexical", agent_lexical, server))

    # TODO: uncomment once you've added the MCP tool
    # print("\n--- Config B: lexical + semantic ---")
    # results.append(run_config("semantic", agent_semantic, server))

    print("\n" + "=" * 60)
    print(f"{'Config':<12} {'Events':>7} {'Wall':>8} {'Cost':>10}")
    print("-" * 60)
    for r in results:
        print(f"{r['label']:<12} {r['events']:>7} {r['wall']:>7.1f}s ${r['cost']:>9.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
