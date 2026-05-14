"""P06 starter — run with local workspace, no security analyzer.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_safety.py
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python run_safety.py --docker

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    AGENT_SERVER (default http://127.0.0.1:18000)
                    WORKSPACE_DIR (default current directory)
"""

import os
import sys
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
    resolve_server_working_dir,
)

# Try different prompts to test risk levels:
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


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    use_docker = "--docker" in sys.argv
    working_dir = resolve_host_working_dir() if use_docker else resolve_server_working_dir()

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    agent = get_default_agent(llm=llm, cli_mode=True)

    # TODO: wire security_policy_filename into the Agent:
    # agent = Agent(llm=llm, tools=tools, security_policy_filename="org_security_policy.j2")

    if use_docker:
        # TODO: switch to DockerWorkspace
        # Before constructing DockerWorkspace, run `docker info` and print a
        # clear error if Docker is missing or stopped.
        # from openhands.workspace import DockerWorkspace
        # workspace = DockerWorkspace(
        #     server_image="ghcr.io/openhands/agent-server:latest-python",
        #     host_port=8010,
        #     mount_dir=str(working_dir),
        # )
        print("Docker mode not yet implemented — fill in the TODO!", file=sys.stderr)
        raise SystemExit(1)
    else:
        workspace = Workspace(
            host=server,
            api_key=resolve_api_key(),
            working_dir=working_dir,
        )

    prompt_key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PROMPTS else "read"
    prompt = PROMPTS[prompt_key]

    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    # TODO: wire security analyzer and confirmation policy:
    # from openhands.sdk.security import (
    #     ConfirmRisky,
    #     EnsembleSecurityAnalyzer,
    #     LLMSecurityAnalyzer,
    #     PatternSecurityAnalyzer,
    #     PolicyRailSecurityAnalyzer,
    #     SecurityRisk,
    # )
    # analyzer = EnsembleSecurityAnalyzer(
    #     analyzers=[
    #         PolicyRailSecurityAnalyzer(),
    #         PatternSecurityAnalyzer(),
    #         LLMSecurityAnalyzer(),
    #     ],
    # )
    # conversation.set_security_analyzer(analyzer)
    # conversation.set_confirmation_policy(ConfirmRisky(threshold=SecurityRisk.MEDIUM))
    #
    # TODO: once ConfirmRisky is enabled, use a non-blocking run loop for terminal
    # scripts. If the remote conversation reaches waiting_for_confirmation,
    # print the pending action and ask the learner to approve or reject it.

    try:
        t0 = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall = time.time() - t0

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"\nprompt: {prompt_key} -> {prompt}")
        print(f"wall: {wall:.1f}s  cost: ${cost:.4f}")
    finally:
        conversation.close()


if __name__ == "__main__":
    main()
