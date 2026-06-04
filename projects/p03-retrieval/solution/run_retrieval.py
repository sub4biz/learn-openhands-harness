"""P03 solution - run lexical-only and lexical+MCP configs, compare.

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
from openhands.tools.task_tracker import TaskTrackerTool
from _runtime import (
    resolve_api_key,
    resolve_host_working_dir,
    resolve_server_working_dir as resolve_working_dir,
    server_visible_path,
)

PROMPT = (
    "Find every place VITE_BACKEND_HOST and VITE_BACKEND_BASE_URL are read or set, "
    "and write a short note explaining how the dev script picks the backend."
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
P03_DIR = Path(__file__).resolve().parents[1]

# Also try this synonym-gap prompt to see when semantic earns its slot:
PROMPT_SYNONYM = (
    "How does the canvas pick which backend to talk to?"
)


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


def run_config(
    label: str,
    agent: Agent,
    server: str,
    working_dir: str,
    prompt: str = PROMPT,
    max_iterations: int | None = None,
) -> dict:
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=working_dir,
    )
    kwargs = {}
    if max_iterations is not None:
        kwargs["max_iteration_per_run"] = max_iterations
    conversation = Conversation(agent=agent, workspace=workspace, **kwargs)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(prompt)
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
                    "query": PROMPT_SYNONYM,
                    "max_results": 5,
                }
            )
        )
        print(observation.visualize.plain)


def run_mcp_live_smoke() -> None:
    """Run one remote model call that must use the MCP search tool."""
    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    working_dir = resolve_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    agent = Agent(llm=llm, tools=[], mcp_config=build_mcp_config(working_dir))
    result = run_config(
        "mcp-live-smoke",
        agent,
        server,
        working_dir,
        (
            "Use the search_code tool once with query "
            "'backend proxy VITE_BACKEND_HOST VITE_BACKEND_BASE_URL'. Then answer with the top two "
            "file paths only. Do not edit files."
        ),
        max_iterations=3,
    )
    print("\n" + "=" * 60)
    print(f"{'Config':<20} {'Events':>7} {'MCP':>5} {'Wall':>8} {'Cost':>10}")
    print("-" * 60)
    print(
        f"{result['label']:<20} {result['events']:>7} {result['search_code']:>5} "
        f"{result['wall']:>7.1f}s ${result['cost']:>9.4f}"
    )
    print("=" * 60)
    if result["search_code"] < 1:
        raise SystemExit("MCP live smoke did not call search_code.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the P03 retrieval experiment.")
    parser.add_argument(
        "--mcp-smoke",
        action="store_true",
        help="Test search_code without model calls.",
    )
    parser.add_argument(
        "--mcp-live-smoke",
        action="store_true",
        help="Run one short remote conversation that must call search_code.",
    )
    parser.add_argument(
        "--exact-semantic",
        action="store_true",
        help="Also run the exact-match prompt with MCP attached.",
    )
    parser.add_argument(
        "--skip-mcp",
        action="store_true",
        help="Run lexical-only configs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mcp_smoke:
        run_mcp_smoke()
        return
    if args.mcp_live_smoke:
        run_mcp_live_smoke()
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
        Tool(name=TaskTrackerTool.name),
    ]
    agent_lexical = Agent(llm=llm, tools=lexical_tools)

    # --- Config B: lexical + MCP search ---
    # This stdio server runs inside the agent-server process. In Dockerized
    # Agent Canvas, the tutorial repo and target repo must both be visible under
    # /projects or another AGENT_WORKSPACE_* mapping.
    mcp_config = build_mcp_config(working_dir)
    agent_semantic = Agent(llm=llm, tools=lexical_tools, mcp_config=mcp_config)

    results = []

    print("\n--- Config A: lexical, exact-match prompt ---")
    results.append(run_config("lexical-exact", agent_lexical, server, working_dir, PROMPT))

    print("\n--- Config A: lexical, synonym prompt ---")
    results.append(
        run_config("lexical-synonym", agent_lexical, server, working_dir, PROMPT_SYNONYM)
    )

    if not args.skip_mcp:
        if args.exact_semantic:
            print("\n--- Config B: lexical + MCP, exact-match prompt ---")
            results.append(
                run_config("mcp-exact", agent_semantic, server, working_dir, PROMPT)
            )

        print("\n--- Config B: lexical + MCP, synonym prompt ---")
        results.append(
            run_config("mcp-synonym", agent_semantic, server, working_dir, PROMPT_SYNONYM)
        )

    print("\n" + "=" * 60)
    print(f"{'Config':<20} {'Events':>7} {'MCP':>5} {'Wall':>8} {'Cost':>10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['label']:<20} {r['events']:>7} {r['search_code']:>5} "
            f"{r['wall']:>7.1f}s ${r['cost']:>9.4f}"
        )
    print("=" * 60)
    print("\nIf lexical-synonym is already correct and cheap, keep MCP off by default.")
    print("If mcp-synonym uses search_code and reduces misses, that is evidence to enable it.")


if __name__ == "__main__":
    main()
