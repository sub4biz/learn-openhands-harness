"""P02 starter — run a single flagship model. Add small + router configs.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_routing.py

Required env vars:  LLM_API_KEY
Optional:           LLM_MODEL (default anthropic/claude-sonnet-4-5-20250929)
                    LLM_MODEL_SMALL, P02_PROMPT, AGENT_SERVER, WORKSPACE_DIR
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
    resolve_server_working_dir as resolve_working_dir,
    token_counts,
)

DEFAULT_PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SMALL_MODEL = "anthropic/claude-haiku-4-5-20251001"
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
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def run_config(label: str, llm: LLM, server: str, working_dir: str, prompt: str) -> dict:
    """Run the prompt with the given LLM and return metrics."""
    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=working_dir,
    )
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall = time.time() - t0

        metrics = conversation.conversation_stats.get_combined_metrics()
        prompt_tokens, completion_tokens = token_counts(metrics)
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": metrics.accumulated_cost,
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
        }
    finally:
        conversation.close()


def choose_llm_for_prompt(prompt: str, flagship_llm: LLM, small_llm: LLM) -> tuple[str, LLM]:
    """TODO: tune this policy for your task family."""
    lowered = prompt.lower()
    if any(marker in lowered for marker in FLAGSHIP_MARKERS):
        return "flagship", flagship_llm
    return "small", small_llm


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model_flagship = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    model_small = os.environ.get("LLM_MODEL_SMALL", DEFAULT_SMALL_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    working_dir = resolve_working_dir()
    prompt = os.environ.get("P02_PROMPT", DEFAULT_PROMPT)

    # --- Config A: flagship ---
    flagship_llm = LLM(
        usage_id="agent",
        model=model_flagship,
        api_key=SecretStr(api_key),
    )

    # TODO: Config B — create a small_llm using LLM_MODEL_SMALL env var.
    # small_llm = LLM(
    #     usage_id="agent-small",
    #     model=model_small,
    #     api_key=SecretStr(api_key),
    # )

    # TODO: Config C — choose one concrete LLM before creating the remote agent.
    # RouterLLM instances do not currently survive RemoteConversation
    # serialization in SDK 1.22.x; pre-conversation routing does.
    # route, routed_llm = choose_llm_for_prompt(prompt, flagship_llm, small_llm)

    results = []

    print(f"\nprompt: {prompt}")

    print("\n--- Config A: flagship ---")
    results.append(run_config("flagship", flagship_llm, server, working_dir, prompt))

    # TODO: uncomment once you've created small_llm and routed_llm.
    # print("\n--- Config B: small ---")
    # results.append(run_config("small", small_llm, server, working_dir, prompt))
    #
    # print(f"\n--- Config C: routed -> {route} ---")
    # results.append(run_config(f"routed->{route}", routed_llm, server, working_dir, prompt))

    print("\n" + "=" * 70)
    print(f"{'Config':<12} {'Events':>7} {'Wall':>8} {'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['label']:<12} {r['events']:>7} {r['wall']:>7.1f}s ${r['cost']:>9.4f} {r['tokens_in']:>12} {r['tokens_out']:>12}")
    print("=" * 70)


if __name__ == "__main__":
    main()
