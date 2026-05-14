"""harness.py — your custom OpenHands harness (starter skeleton).

Wire in the artifacts you kept from P01-P07a. Fill in every TODO block.

Run with:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python harness.py "your task prompt"

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    LLM_MODEL_FLAGSHIP, LLM_MODEL_SMALL, WORKSPACE_DIR
                    HARNESS_SECURITY_POLICY, HARNESS_PORT
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


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def model_env(primary: str, fallback: str, default: str = DEFAULT_MODEL) -> str:
    return os.environ.get(primary) or os.environ.get(fallback, default)


# --- P02: model + routing ---------------------------------------------------
# TODO: paste your P02 routing policy or LLMRegistry config here.
# Keep routing outside the RemoteConversation boundary: choose one concrete LLM
# for the task, then build the agent with that LLM.

api_key = SecretStr(require_env("LLM_API_KEY"))

flagship_llm = LLM(
    usage_id="agent",
    model=model_env("LLM_MODEL_FLAGSHIP", "LLM_MODEL"),
    api_key=api_key,
)

# TODO: small_llm = LLM(
#     usage_id="agent-small",
#     model=os.environ.get("LLM_MODEL_SMALL", DEFAULT_SMALL_MODEL),
#     api_key=api_key,
# )


def choose_llm_for_task(task: str) -> LLM:
    """TODO: replace this with the routing policy you kept from P02."""
    _ = task
    return flagship_llm


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
# TODO: paste your P07a critic result here. Keep this disabled unless the
# repeated-run table showed a real pass-rate or cost-per-pass improvement.
#
# Working shape:
# from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig
# iterative = IterativeRefinementConfig(
#     success_threshold=float(os.environ.get("CRITIC_SUCCESS_THRESHOLD", "0.7")),
#     max_iterations=int(os.environ.get("CRITIC_MAX_ITERATIONS", "3")),
# )
# critic = APIBasedCritic(
#     server_url=os.environ["CRITIC_SERVER_URL"],
#     api_key=os.environ.get("CRITIC_API_KEY", api_key.get_secret_value()),
#     model_name=os.environ.get("CRITIC_MODEL_NAME", "critic"),
#     iterative_refinement=iterative,
# )
critic = None

# --- P06: security profile --------------------------------------------------
# TODO: point this at your kept org_security_policy.j2. DockerWorkspace only
# mounts the target repo by default, so mount the policy directory separately.
security_policy_host_path = Path(
    os.environ.get(
        "HARNESS_SECURITY_POLICY",
        str(
            Path(__file__).parents[2]
            / "p06-safety"
            / "solution"
            / "org_security_policy.j2"
        ),
    )
).expanduser().resolve()

if not security_policy_host_path.exists():
    print(f"Missing security policy: {security_policy_host_path}", file=sys.stderr)
    raise SystemExit(2)

security_policy_filename = f"/openhands-harness-policy/{security_policy_host_path.name}"
security_policy_volume = f"{security_policy_host_path.parent}:/openhands-harness-policy:ro"

security_analyzer = EnsembleSecurityAnalyzer(
    analyzers=[
        PolicyRailSecurityAnalyzer(),
        PatternSecurityAnalyzer(),
        LLMSecurityAnalyzer(),
    ],
)

# --- P06: sandbox -----------------------------------------------------------
def main(task: str) -> None:
    # TODO: add critic=critic if you kept one from P07a.
    agent = Agent(
        llm=choose_llm_for_task(task),
        tools=tools,
        security_policy_filename=security_policy_filename,
        critic=critic,
    )

    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        # P06 uses 8010 in its examples. P07 defaults to 8020 so the two
        # lessons do not collide if both are running.
        host_port=int(os.environ.get("HARNESS_PORT", "8020")),
        mount_dir=str(resolve_host_working_dir()),
        volumes=[security_policy_volume],
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
