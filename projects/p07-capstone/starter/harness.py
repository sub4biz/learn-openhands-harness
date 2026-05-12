"""harness.py — your custom OpenHands harness (starter skeleton).

Wire in the artifacts you kept from P01-P07a. Fill in every TODO block.

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
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.workspace import DockerWorkspace

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"


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
# TODO: paste your RouterLLM or LLMRegistry config here.
# You need at least: flagship_llm, small_llm, and agent_llm (the router).

api_key = SecretStr(require_env("LLM_API_KEY"))

flagship_llm = LLM(
    usage_id="agent",
    model=model_env("LLM_MODEL_FLAGSHIP", "LLM_MODEL"),
    api_key=api_key,
)

# TODO: small_llm = LLM(...)
# TODO: agent_llm = MultimodalRouter(...) or your custom RouterLLM

# --- supporting note: tool surface ------------------------------------------
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]

# --- P03: retrieval ---------------------------------------------------------
# TODO: paste your MCP decision rule as a comment. If MCP is on, configure it.
# Default: lexical only.

# --- P04: decomposition -----------------------------------------------------
# TODO: paste your decomposition rule as a comment. Use it to decide when a
# task should run as one prompt and when the harness should split it into
# scoped prompts plus an aggregation step.

# --- P07a: critic + iterative refinement ------------------------------------
# TODO: paste your Critic + IterativeRefinementConfig block here, or remove
# this section if the critic didn't earn its slot for your task type.

# --- P06: security profile --------------------------------------------------
# TODO: point this at your kept org_security_policy.j2
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
# TODO: replace flagship_llm with agent_llm (your router) once it's wired up.
# TODO: add critic=critic if you kept one from P07a.
agent = Agent(
    llm=flagship_llm,
    tools=tools,
    security_policy_filename=security_policy_filename,
)


# --- P06: sandbox -----------------------------------------------------------
def main(task: str) -> None:
    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        host_port=int(os.environ.get("HARNESS_PORT", "8010")),
        mount_dir=resolve_working_dir(),
    ) as workspace:
        # P05: AGENTS.md is read automatically if it sits at the root of the
        # working directory mounted into the workspace. Make sure your kept
        # AGENTS.md is committed to the repo you point this at.

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
