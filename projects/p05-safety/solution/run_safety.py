"""P05 solution — security analyzer + confirmation policy + Docker sandbox.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_safety.py [read|edit|network|delete]
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python run_safety.py --docker [read|edit|network|delete]

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import os
import sys
import time
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Agent, Conversation, RemoteConversation, Workspace
from openhands.sdk.tool import Tool
from openhands.sdk.security import (
    ConfirmRisky,
    EnsembleSecurityAnalyzer,
    LLMSecurityAnalyzer,
    PatternSecurityAnalyzer,
    PolicyRailSecurityAnalyzer,
    SecurityRisk,
)
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool

PROMPTS = {
    "read": "List the files and summarize the repo layout.",
    "edit": "Create NOTES.md with three facts about this repo.",
    "network": "Install the 'requests' package.",
    "delete": "Delete the NOTES.md file you just created.",
}

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
    use_docker = "--docker" in sys.argv
    working_dir = resolve_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    security_analyzer = EnsembleSecurityAnalyzer(
        analyzers=[
            PolicyRailSecurityAnalyzer(),
            PatternSecurityAnalyzer(),
            LLMSecurityAnalyzer(),
        ],
    )

    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ]

    policy_path = Path(__file__).parent / "org_security_policy.j2"
    agent = Agent(
        llm=llm,
        tools=tools,
        security_policy_filename=str(policy_path),
    )

    if use_docker:
        from openhands.workspace import DockerWorkspace
        workspace = DockerWorkspace(
            server_image="ghcr.io/openhands/agent-server:latest-python",
            host_port=8010,
            mount_dir=working_dir,
        )
    else:
        workspace = Workspace(
            host=server,
            api_key=resolve_api_key(),
            working_dir=working_dir,
        )

    # Parse prompt key from args (skip --docker)
    args = [a for a in sys.argv[1:] if a != "--docker"]
    prompt_key = args[0] if args and args[0] in PROMPTS else "read"
    prompt = PROMPTS[prompt_key]

    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    conversation.set_security_analyzer(security_analyzer)
    conversation.set_confirmation_policy(ConfirmRisky(threshold=SecurityRisk.MEDIUM))

    try:
        t0 = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall = time.time() - t0

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"\nprompt: {prompt_key} -> {prompt}")
        print(f"docker: {use_docker}")
        print(f"wall: {wall:.1f}s  cost: ${cost:.4f}")
    finally:
        conversation.close()


if __name__ == "__main__":
    main()
