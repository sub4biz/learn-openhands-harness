"""P05 starter — run with local workspace, no security analyzer.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_safety.py
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python run_safety.py --docker

Required env vars:  LLM_API_KEY, LLM_MODEL
Optional:           AGENT_SERVER (default http://127.0.0.1:18000)
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent

# Try different prompts to test risk levels:
PROMPTS = {
    "read": "List the files and summarize the repo layout.",
    "edit": "Create NOTES.md with three facts about this repo.",
    "network": "Install the 'requests' package.",
    "delete": "Delete the NOTES.md file you just created.",
}


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


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = require_env("LLM_MODEL")
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    use_docker = "--docker" in sys.argv

    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))

    # TODO: create a security_llm for the analyzer (can be a cheap model)
    # security_llm = LLM(usage_id="security", model="...", api_key=SecretStr(api_key))

    agent = get_default_agent(llm=llm, cli_mode=True)

    # TODO: wire security_policy_filename into the Agent:
    # agent = Agent(llm=llm, tools=tools, security_policy_filename="org_security_policy.j2")

    if use_docker:
        # TODO: switch to DockerWorkspace
        # from openhands.workspace import DockerWorkspace
        # workspace = DockerWorkspace(
        #     server_image="ghcr.io/openhands/agent-server:latest-python",
        #     host_port=8010,
        # )
        print("Docker mode not yet implemented — fill in the TODO!", file=sys.stderr)
        raise SystemExit(1)
    else:
        workspace = Workspace(
            host=server,
            api_key=resolve_api_key(),
            working_dir=tempfile.mkdtemp(prefix="p05_safety_"),
        )

    prompt_key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in PROMPTS else "read"
    prompt = PROMPTS[prompt_key]

    conversation = Conversation(agent=agent, workspace=workspace, visualize=True)
    assert isinstance(conversation, RemoteConversation)

    # TODO: wire security analyzer and confirmation policy:
    # from openhands.sdk.security.confirmation_policy import ConfirmRisky
    # from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
    # conversation.set_security_analyzer(LLMSecurityAnalyzer(llm=security_llm))
    # conversation.set_confirmation_policy(ConfirmRisky())

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
