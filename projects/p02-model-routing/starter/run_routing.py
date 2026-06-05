"""P02 starter: run a single flagship model, then add small and routed configs.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_routing.py

Required env vars:
    LLM_API_KEY

Optional env vars:
    LLM_MODEL, LLM_MODEL_SMALL, P02_PROMPT, AGENT_SERVER, WORKSPACE_DIR
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from _runtime import load_dotenv, resolve_api_key, resolve_server_working_dir, token_counts

load_dotenv(PROJECTS_DIR)

from pydantic import SecretStr

from openhands.sdk import Conversation, LLM, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent


DEFAULT_PROMPT = (
    "Find every place VITE_BACKEND_HOST and VITE_BACKEND_BASE_URL are read or set, "
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


def run_config(label: str, llm: LLM, server: str, working_dir: str, prompt: str) -> dict[str, object]:
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
        started = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall_seconds = time.time() - started

        metrics = conversation.conversation_stats.get_combined_metrics()
        tokens_in, tokens_out = token_counts(metrics)
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall_seconds,
            "cost": float(metrics.accumulated_cost or 0.0),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
    finally:
        conversation.close()


def choose_llm_for_prompt(prompt: str, flagship_llm: LLM, small_llm: LLM) -> tuple[str, LLM]:
    """TODO: tune this policy for your task family."""
    lowered = prompt.lower()
    if any(marker in lowered for marker in FLAGSHIP_MARKERS):
        return "flagship", flagship_llm
    return "small", small_llm


def print_results(results: list[dict[str, object]]) -> None:
    print("\n" + "=" * 70)
    print(f"{'Config':<14} {'Events':>7} {'Wall':>8} {'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}")
    print("-" * 70)
    for result in results:
        print(
            f"{result['label']:<14} {result['events']:>7} {result['wall']:>7.1f}s "
            f"${result['cost']:>9.4f} {result['tokens_in']:>12} {result['tokens_out']:>12}"
        )
    print("=" * 70)


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model_flagship = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    model_small = os.environ.get("LLM_MODEL_SMALL", DEFAULT_SMALL_MODEL)
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")
    working_dir = resolve_server_working_dir()
    prompt = os.environ.get("P02_PROMPT", DEFAULT_PROMPT)

    flagship_llm = LLM(
        usage_id="agent-flagship",
        model=model_flagship,
        api_key=SecretStr(api_key),
    )

    # TODO: Config B. Create a small_llm using model_small.
    # small_llm = LLM(
    #     usage_id="agent-small",
    #     model=model_small,
    #     api_key=SecretStr(api_key),
    # )

    # TODO: Config C. Choose one concrete LLM before creating the remote agent.
    # route, routed_llm = choose_llm_for_prompt(prompt, flagship_llm, small_llm)

    print(f"\nprompt: {prompt}")

    results = []
    print("\n--- Config A: flagship ---")
    results.append(run_config("flagship", flagship_llm, server, working_dir, prompt))

    # TODO: uncomment after creating small_llm and routed_llm.
    # print("\n--- Config B: small ---")
    # results.append(run_config("small", small_llm, server, working_dir, prompt))
    #
    # print(f"\n--- Config C: routed -> {route} ---")
    # results.append(run_config(f"routed->{route}", routed_llm, server, working_dir, prompt))

    print_results(results)


if __name__ == "__main__":
    main()
