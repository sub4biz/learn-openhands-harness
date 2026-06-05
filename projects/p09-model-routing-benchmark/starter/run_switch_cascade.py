"""P09 starter: cascading model routing with SwitchLLMTool.

Run one Canvas-visible cascade smoke task:
    LLM_API_KEY=... uv run --with openhands-sdk --with openhands-tools --with pytest python run_switch_cascade.py --setup-profiles --save-profile-secrets --task p09-task-08

The rules router in run_routing.py chooses the starting profile. This file
teaches the second routing strategy: switch profiles during the conversation
when evidence says the current model is stuck.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from pydantic import SecretStr

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = PROJECT_DIR.parents[0]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from _runtime import resolve_api_key, server_visible_path, token_counts
from openhands.sdk import Conversation, LLM, Workspace
from openhands.sdk.llm import LLMProfileStore
from openhands.tools.preset.default import get_default_agent
from run_routing import DEFAULT_MODELS, Task, build_prompt, check_task, load_tasks, prepare_repo, route_by_rules


PROFILE_NAMES = {
    "cheap": "p09-cheap",
    "mid": "p09-mid",
    "frontier": "p09-frontier",
}


def model_for_tier(tier: str) -> str:
    return os.environ.get(f"P09_MODEL_{tier.upper()}", DEFAULT_MODELS[tier])


def save_profiles(include_secrets: bool) -> None:
    api_key = os.environ.get("LLM_API_KEY")
    secret = SecretStr(api_key) if api_key else None
    store = LLMProfileStore()
    for tier, profile_name in PROFILE_NAMES.items():
        store.save(
            profile_name,
            LLM(
                model=model_for_tier(tier),
                api_key=secret,
                base_url=os.environ.get("LLM_BASE_URL"),
                usage_id=f"starter-profile:{profile_name}",
            ),
            include_secrets=include_secrets,
        )


def find_task(task_id: str) -> Task:
    for task in load_tasks():
        if task.id == task_id:
            return task
    raise SystemExit(f"unknown task id: {task_id}")


def switch_instruction(task: Task, initial_tier: str) -> str:
    # TODO: tighten these criteria after you inspect the first Canvas trace.
    return (
        "Model switching policy for this run:\n"
        f"- Start on `{PROFILE_NAMES[initial_tier]}`.\n"
        f"- Available profiles: `{PROFILE_NAMES['cheap']}`, `{PROFILE_NAMES['mid']}`, "
        f"`{PROFILE_NAMES['frontier']}`.\n"
        "- If the same test fails twice, the same error repeats, the same file "
        "is edited three times, or progress stalls, call `switch_llm` before "
        "continuing.\n"
        "- Switch to `p09-mid` for routine debugging.\n"
        "- Switch to `p09-frontier` for async races, security/auth work, or "
        "architecture work.\n"
        "- Include the evidence in the switch reason.\n\n"
        f"Task tags: {', '.join(task.tags)}"
    )


def run_task(task: Task, args: argparse.Namespace) -> dict[str, object]:
    repo = prepare_repo(task, "cascade_switch")
    initial_tier = route_by_rules(task)
    api_key = os.environ.get("LLM_API_KEY")
    secret = SecretStr(api_key) if api_key else None
    llm = LLM(
        model=model_for_tier(initial_tier),
        api_key=secret,
        base_url=os.environ.get("LLM_BASE_URL"),
        usage_id=f"starter-cascade:{initial_tier}",
    )

    agent = get_default_agent(llm=llm, cli_mode=True)
    include_default_tools = list(agent.include_default_tools)
    if "SwitchLLMTool" not in include_default_tools:
        include_default_tools.append("SwitchLLMTool")
    agent = agent.model_copy(update={"include_default_tools": include_default_tools})

    workspace = Workspace(
        host=args.agent_server,
        api_key=resolve_api_key(),
        working_dir=server_visible_path(repo),
    )
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        max_iteration_per_run=args.max_iterations,
        stuck_detection=True,
    )

    prompt = switch_instruction(task, initial_tier) + "\n\n" + build_prompt(task, repo)
    started = time.time()
    passed = False
    try:
        conversation.send_message(prompt)
        conversation.run()
        check_task(repo, task.id)
        passed = True
    finally:
        wall = time.time() - started
        metrics = conversation.conversation_stats.get_combined_metrics()
        tokens_in, tokens_out = token_counts(metrics)
        conversation_id = str(conversation.id)
        conversation.close()

    print(f"Canvas URL: {args.agent_server.rstrip('/')}/conversations/{conversation_id}")
    return {
        "task": task.id,
        "strategy": "cascade",
        "initial_model": initial_tier,
        "passed": passed,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": float(metrics.accumulated_cost or 0.0),
        "wall": wall,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="p09-task-08")
    parser.add_argument("--agent-server", default=os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000"))
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("P09_MAX_ITERATIONS", "40")))
    parser.add_argument("--setup-profiles", action="store_true")
    parser.add_argument("--save-profile-secrets", action="store_true")
    args = parser.parse_args()

    if args.setup_profiles:
        save_profiles(args.save_profile_secrets)

    print(run_task(find_task(args.task), args))


if __name__ == "__main__":
    main()
