"""P02 starter — run a single flagship model. Add small + router configs.

Run with:
    uv run --with openhands-sdk --with openhands-tools python run_routing.py

Required env vars:  LLM_API_KEY, LLM_MODEL
Optional:           LLM_MODEL_SMALL, AGENT_SERVER
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.tools.preset.default import get_default_agent

PROMPT = (
    "Find every place VITE_BACKEND_HOST is read or set, "
    "and write a short note explaining how the dev script picks the backend."
)


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


def run_config(label: str, llm: LLM, server: str) -> dict:
    """Run the prompt with the given LLM and return metrics."""
    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(
        host=server,
        api_key=resolve_api_key(),
        working_dir=tempfile.mkdtemp(prefix=f"p02_{label}_"),
    )
    conversation = Conversation(agent=agent, workspace=workspace, visualize=True)
    assert isinstance(conversation, RemoteConversation)

    try:
        t0 = time.time()
        conversation.send_message(PROMPT)
        conversation.run()
        wall = time.time() - t0

        metrics = conversation.conversation_stats.get_combined_metrics()
        return {
            "label": label,
            "events": len(conversation.state.events),
            "wall": wall,
            "cost": metrics.accumulated_cost,
            "tokens_in": metrics.accumulated_prompt_tokens,
            "tokens_out": metrics.accumulated_completion_tokens,
        }
    finally:
        conversation.close()


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model_flagship = require_env("LLM_MODEL")
    server = os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000")

    # --- Config A: flagship ---
    flagship_llm = LLM(
        usage_id="agent",
        model=model_flagship,
        api_key=SecretStr(api_key),
    )

    # TODO: Config B — create a small_llm using LLM_MODEL_SMALL env var
    # small_llm = LLM(...)

    # TODO: Config C — create a RouterLLM that mixes flagship and small.
    # Start with MultimodalRouter or write a keyword-based router.
    # from openhands.sdk.llm.router import MultimodalRouter
    # router_llm = MultimodalRouter(
    #     usage_id="agent-router",
    #     llms_for_routing={"primary": flagship_llm, "secondary": small_llm},
    # )

    results = []

    print("\n--- Config A: flagship ---")
    results.append(run_config("flagship", flagship_llm, server))

    # TODO: uncomment once you've created small_llm and router_llm
    # print("\n--- Config B: small ---")
    # results.append(run_config("small", small_llm, server))
    #
    # print("\n--- Config C: routed ---")
    # results.append(run_config("routed", router_llm, server))

    print("\n" + "=" * 70)
    print(f"{'Config':<12} {'Events':>7} {'Wall':>8} {'Cost':>10} {'Tokens in':>12} {'Tokens out':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['label']:<12} {r['events']:>7} {r['wall']:>7.1f}s ${r['cost']:>9.4f} {r['tokens_in']:>12} {r['tokens_out']:>12}")
    print("=" * 70)


if __name__ == "__main__":
    main()
