"""P03 starter - run lexical search, then wire the included MCP server.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_retrieval.py

Cheap MCP smoke test:
    uv run --with openhands-sdk --with openhands-tools python run_retrieval.py --mcp-smoke

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
                    P03_MCP_PYTHON (default python, used by the agent server)
"""

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr
from openhands.sdk import LLM, Agent, Conversation, RemoteConversation, Workspace
from openhands.sdk.tool import Tool
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from _runtime import (
    resolve_api_key,
    resolve_host_working_dir,
    resolve_server_working_dir as resolve_working_dir,
    server_visible_path,
)

PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
P03_DIR = Path(__file__).resolve().parents[1]


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def build_mcp_config(
    search_root: str,
    *,
    script_path: str | None = None,
    command: str | None = None,
) -> dict:
    """Return a stdio MCP config for the included repo search server."""
    script = script_path or os.environ.get("P03_MCP_SERVER_PATH")
    if script is None:
        script = server_visible_path(P03_DIR / "code_search_mcp.py")
    return {
        "mcpServers": {
            "repo-code-search": {
                "command": command or os.environ.get("P03_MCP_PYTHON", "python"),
                "args": [script],
                "env": {"CODE_SEARCH_ROOT": search_root},
                "cwd": str(Path(script).parent),
            }
        }
    }


def count_tool_calls(events) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events:
        event_type = type(event).__name__
        if event_type != "ActionEvent" and not hasattr(event, "tool_input"):
            continue
        tool = getattr(event, "tool", None) or getattr(event, "tool_name", None)
        if tool:
            counts[str(tool)] += 1
    return counts


def run_config(label: str, agent: Agent, server: str, working_dir: str) -> dict:
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
        tool_counts = count_tool_calls(conversation.state.events)
        return {
            "label": label,
            "events": len(conversation.state.events),
            "search_code": tool_counts.get("search_code", 0),
            "wall": wall,
            "cost": metrics.accumulated_cost,
        }
    finally:
        conversation.close()


def run_mcp_smoke() -> None:
    """Validate the included MCP server without model calls."""
    from openhands.sdk.mcp import create_mcp_tools

    workspace = resolve_host_working_dir()
    config = build_mcp_config(
        str(workspace),
        script_path=str(P03_DIR / "code_search_mcp.py"),
        command=sys.executable,
    )
    with create_mcp_tools(config, timeout=30) as client:
        tool_names = [tool.name for tool in client]
        print(f"MCP tools: {', '.join(tool_names)}")
        search_tool = next(tool for tool in client if tool.name == "search_code")
        observation = search_tool(
            search_tool.action_from_arguments(
                {
                    "query": "How does the canvas pick which backend to talk to?",
                    "max_results": 5,
                }
            )
        )
        print(observation.visualize.plain)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the P03 retrieval experiment.")
    parser.add_argument(
        "--mcp-smoke",
        action="store_true",
        help="Test search_code without model calls.",
    )
    args = parser.parse_args()
    if args.mcp_smoke:
        run_mcp_smoke()
        return

    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    working_dir = resolve_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    # --- Config A: lexical only ---
    lexical_tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ]
    agent_lexical = Agent(llm=llm, tools=lexical_tools)

    # TODO: Config B - add the included MCP search tool.
    # mcp_config = build_mcp_config(working_dir)
    # agent_semantic = Agent(llm=llm, tools=lexical_tools, mcp_config=mcp_config)

    results = []

    print("\n--- Config A: lexical only ---")
    results.append(run_config("lexical", agent_lexical, server, working_dir))

    # TODO: uncomment once you've added the MCP tool
    # print("\n--- Config B: lexical + MCP search ---")
    # results.append(run_config("semantic", agent_semantic, server, working_dir))

    print("\n" + "=" * 60)
    print(f"{'Config':<12} {'Events':>7} {'MCP':>5} {'Wall':>8} {'Cost':>10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['label']:<12} {r['events']:>7} {r['search_code']:>5} "
            f"{r['wall']:>7.1f}s ${r['cost']:>9.4f}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
