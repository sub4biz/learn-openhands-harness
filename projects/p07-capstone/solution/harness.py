"""harness.py — your custom OpenHands harness (complete capstone).

Wires together all kept artifacts from P01-P07a:
  P02: model routing (remote-safe pre-conversation policy)
  P03: retrieval decision (lexical only, comment explains when to add MCP)
  P04: decomposition decision rule
  P05: memory (AGENTS.md loaded automatically from workspace)
  P06: security policy + DockerWorkspace + ConfirmRisky
  P07a: optional APIBasedCritic + iterative refinement

Run with:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python harness.py "your task prompt"

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    LLM_MODEL_FLAGSHIP, LLM_MODEL_SMALL, WORKSPACE_DIR
                    HARNESS_ENABLE_CRITIC, CRITIC_SERVER_URL,
                    CRITIC_API_KEY, CRITIC_MODEL_NAME
"""

import os
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, RemoteConversation
from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig
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
from openhands.workspace import DockerWorkspace
from _runtime import resolve_host_working_dir

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SMALL_MODEL = "anthropic/claude-haiku-4-5-20251001"
DEFAULT_CRITIC_SERVER_URL = "https://llm-proxy.app.all-hands.dev/vllm"
FLAGSHIP_MARKERS = (
    "image",
    "screenshot",
    "diagram",
    "large refactor",
    "security",
    "architecture",
    "multi-file edit",
)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def model_env(primary: str, fallback: str, default: str = DEFAULT_MODEL) -> str:
    return os.environ.get(primary) or os.environ.get(fallback, default)


def env_enabled(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


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


def choose_llm_for_task(task: str) -> tuple[str, LLM]:
    """Remote-safe routing policy kept from P02."""
    lowered = task.lower()
    if any(marker in lowered for marker in FLAGSHIP_MARKERS):
        return "flagship", flagship_llm
    return "small", small_llm


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
def build_critic_from_env():
    """Build the P07a critic only when the experiment showed it was worth it.

    `success_threshold` is the APIBasedCritic success probability required to
    stop refining. If the critic returns a lower score, Conversation.run()
    sends the critic's follow-up prompt until `max_iterations` is reached.
    """
    if not env_enabled("HARNESS_ENABLE_CRITIC"):
        return None
    iterative = IterativeRefinementConfig(
        success_threshold=float(os.environ.get("CRITIC_SUCCESS_THRESHOLD", "0.7")),
        max_iterations=int(os.environ.get("CRITIC_MAX_ITERATIONS", "3")),
    )
    return APIBasedCritic(
        server_url=os.environ.get("CRITIC_SERVER_URL", DEFAULT_CRITIC_SERVER_URL),
        api_key=SecretStr(os.environ.get("CRITIC_API_KEY", api_key.get_secret_value())),
        model_name=os.environ.get("CRITIC_MODEL_NAME", "critic"),
        iterative_refinement=iterative,
    )


critic = build_critic_from_env()

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


# --- P06: sandbox -----------------------------------------------------------
def main(task: str) -> None:
    route, selected_llm = choose_llm_for_task(task)
    agent = Agent(
        llm=selected_llm,
        tools=tools,
        security_policy_filename=security_policy_filename,
        critic=critic,
    )

    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        # P06 uses 8010 in its examples. Use a different default here so two
        # lessons can run at once; override HARNESS_PORT if it still collides.
        host_port=int(os.environ.get("HARNESS_PORT", "8020")),
        mount_dir=str(resolve_host_working_dir()),
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
        print(
            f"route: {route}  critic: {critic is not None}  "
            f"wall: {wall:.1f}s  cost: ${cost:.4f}"
        )
        convo.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "What does this repo do?")
