"""harness.py — your custom OpenHands harness (complete capstone).

Wires together all kept artifacts from P01-P07a:
  P02: model routing (MultimodalRouter)
  P03: retrieval decision (lexical only, comment explains when to add MCP)
  P04: decomposition decision rule
  P05: memory (AGENTS.md loaded automatically from workspace)
  P06: security policy + DockerWorkspace + ConfirmRisky
  P07a: critic placeholder (uncomment if you kept one)

Run with:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python harness.py "your task prompt"

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    LLM_MODEL_FLAGSHIP, LLM_MODEL_SMALL, WORKSPACE_DIR
"""

import os
import sys
import time
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, RemoteConversation
from openhands.sdk.tool import Tool
from openhands.sdk.security import (
    ConfirmRisky,
    EnsembleSecurityAnalyzer,
    LLMSecurityAnalyzer,
    PatternSecurityAnalyzer,
    PolicyRailSecurityAnalyzer,
    SecurityRisk,
)
from openhands.sdk.llm.router import MultimodalRouter
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.workspace import DockerWorkspace

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SMALL_MODEL = "anthropic/claude-haiku-4-5-20251001"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def model_env(primary: str, fallback: str, default: str = DEFAULT_MODEL) -> str:
    return os.environ.get(primary) or os.environ.get(fallback, default)


def resolve_working_dir() -> str:
    path = Path(os.environ.get("WORKSPACE_DIR", Path.cwd())).expanduser().resolve()
    if not path.exists():
        print(f"WORKSPACE_DIR does not exist: {path}", file=sys.stderr)
        raise SystemExit(2)
    return str(path)


# --- P02: model + routing ---------------------------------------------------
api_key = SecretStr(require_env("LLM_API_KEY"))

flagship_llm = LLM(
    usage_id="agent",
    model=model_env("LLM_MODEL_FLAGSHIP", "LLM_MODEL"),
    api_key=api_key,
)
small_llm = LLM(
    usage_id="agent-small",
    model=os.environ.get("LLM_MODEL_SMALL", DEFAULT_SMALL_MODEL),
    api_key=api_key,
)

# MultimodalRouter: image messages → flagship, text → small.
# Replace with a keyword router for finer control.
agent_llm = MultimodalRouter(
    usage_id="agent-router",
    llms_for_routing={"primary": flagship_llm, "secondary": small_llm},
)

# --- supporting note: tool surface ------------------------------------------
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]

# --- P03: retrieval ---------------------------------------------------------
# Decision rule: lexical only for most repos. Enable MCP semantic search only
# when 30%+ of prompts use terms that don't appear verbatim in source.

# --- P04: decomposition -----------------------------------------------------
# Decision rule: split the task when it has independent review dimensions,
# exact scoped outputs, and failures that can be retried independently. Keep it
# monolithic when the answer needs one shared chain of reasoning.

# --- P07a: critic + iterative refinement ------------------------------------
# Uncomment if you kept a critic from P07a:
# from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig
# iterative = IterativeRefinementConfig(success_threshold=0.7, max_iterations=3)
# critic = APIBasedCritic(
#     server_url=os.environ["CRITIC_SERVER_URL"],
#     api_key=os.environ["CRITIC_API_KEY"],
#     model_name=os.environ["CRITIC_MODEL_NAME"],
#     iterative_refinement=iterative,
# )

# --- P06: security profile --------------------------------------------------
security_policy_filename = os.environ.get(
    "HARNESS_SECURITY_POLICY",
    str(
        Path(__file__).parents[2]
        / "p06-safety"
        / "solution"
        / "org_security_policy.j2"
    ),
)

security_analyzer = EnsembleSecurityAnalyzer(
    analyzers=[
        PolicyRailSecurityAnalyzer(),
        PatternSecurityAnalyzer(),
        LLMSecurityAnalyzer(),
    ],
)

# --- agent -------------------------------------------------------------------
agent = Agent(
    llm=agent_llm,
    tools=tools,
    security_policy_filename=security_policy_filename,
)  # add critic=critic here if you kept one


# --- P06: sandbox -----------------------------------------------------------
def main(task: str) -> None:
    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        host_port=int(os.environ.get("HARNESS_PORT", "8010")),
        mount_dir=resolve_working_dir(),
    ) as workspace:
        # P05: AGENTS.md is read automatically if it sits at the root of the
        # working directory mounted into the workspace.

        convo = Conversation(agent=agent, workspace=workspace)
        assert isinstance(convo, RemoteConversation)

        convo.set_security_analyzer(security_analyzer)
        convo.set_confirmation_policy(ConfirmRisky(threshold=SecurityRisk.MEDIUM))

        t0 = time.time()
        convo.send_message(task)
        convo.run()
        wall = time.time() - t0

        cost = convo.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"wall: {wall:.1f}s  cost: ${cost:.4f}")
        convo.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "What does this repo do?")
