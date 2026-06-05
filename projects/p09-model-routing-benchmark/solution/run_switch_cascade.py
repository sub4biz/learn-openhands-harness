from __future__ import annotations

import argparse
import os
import re
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

from _runtime import load_dotenv, resolve_api_key, server_visible_path, token_counts

load_dotenv(PROJECT_DIR)

from observability import configure_p09_observability

configure_p09_observability(default_mode="auto")

from openhands.sdk import Conversation, LLM, Workspace
from openhands.sdk.llm import LLMProfileStore
from openhands.tools.preset.default import get_default_agent
from routing_core import (
    DEFAULT_MODELS,
    RunResult,
    Task,
    build_task_prompt,
    check_task,
    clean_copy_repo,
    load_tasks,
    metric_totals,
    model_for_tier,
    print_results,
    rules_route,
)


PROFILE_NAMES = {
    "cheap": "p09-cheap",
    "mid": "p09-mid",
    "frontier": "p09-frontier",
}
PROFILE_TO_TIER = {profile: tier for tier, profile in PROFILE_NAMES.items()}


def save_profiles(include_secrets: bool) -> None:
    api_key = os.environ.get("LLM_API_KEY")
    secret = SecretStr(api_key) if api_key else None
    base_url = os.environ.get("LLM_BASE_URL")
    store = LLMProfileStore()
    for tier in DEFAULT_MODELS:
        store.save(
            PROFILE_NAMES[tier],
            LLM(
                model=model_for_tier(tier),
                api_key=secret,
                base_url=base_url,
                usage_id=f"profile:{PROFILE_NAMES[tier]}",
            ),
            include_secrets=include_secrets,
        )
    if include_secrets:
        print("Saved p09 LLM profiles with secrets in ~/.openhands/profiles.")
    else:
        print(
            "Saved p09 LLM profiles without secrets. Use Canvas-created profiles "
            "or rerun with --save-profile-secrets before live switching."
        )


def find_task(task_id: str) -> Task:
    for task in load_tasks():
        if task.id == task_id:
            return task
    raise SystemExit(f"unknown task id: {task_id}")


def switch_instruction(task: Task, initial_tier: str) -> str:
    return (
        "Model switching policy for this run:\n"
        f"- You are starting on profile `{PROFILE_NAMES[initial_tier]}`.\n"
        f"- Available profiles: `{PROFILE_NAMES['cheap']}`, `{PROFILE_NAMES['mid']}`, "
        f"`{PROFILE_NAMES['frontier']}`.\n"
        "- If the same test fails twice, the same error repeats, the same file is "
        "edited three times, or you stop making progress, call `switch_llm` before "
        "continuing.\n"
        "- For routine debugging, switch to `p09-mid`. For async race conditions, "
        "security, auth, or architecture work, switch to `p09-frontier`.\n"
        "- Include a concise evidence-based reason in the switch call.\n\n"
        f"Task tags: {', '.join(task.tags)}"
    )


def extract_switch_reasons(events: list[object]) -> list[str]:
    reasons: list[str] = []
    for event in events:
        try:
            text = str(event.model_dump(mode="json"))
        except Exception:
            text = str(event)
        if "switch_llm" not in text and "Switch LLM" not in text and "profile_name" not in text:
            continue
        profile = re.search(r"profile_name['\"]?: ['\"]([^'\"]+)", text)
        reason = re.search(r"reason['\"]?: ['\"]([^'\"]+)", text)
        if profile:
            label = profile.group(1)
            if reason:
                label = f"{label}: {reason.group(1)}"
            reasons.append(label)
    return reasons


def count_remote_attempts(events: list[object]) -> int:
    completion_logs = sum(1 for event in events if type(event).__name__ == "LLMCompletionLogEvent")
    if completion_logs:
        return completion_logs
    return sum(1 for event in events if type(event).__name__ == "ActionEvent")


def run_switch_task(task: Task, args: argparse.Namespace) -> RunResult:
    run_root = Path(args.run_root).expanduser().resolve()
    repo = clean_copy_repo(task, "cascade_switch", run_root)
    initial_tier = rules_route(task)

    api_key = os.environ.get("LLM_API_KEY")
    secret = SecretStr(api_key) if api_key else None
    llm = LLM(
        model=model_for_tier(initial_tier),
        api_key=secret,
        base_url=os.environ.get("LLM_BASE_URL"),
        usage_id=f"pathb-{initial_tier}",
    )

    agent = get_default_agent(llm=llm, cli_mode=True)
    include_default_tools = list(agent.include_default_tools)
    if "SwitchLLMTool" not in include_default_tools:
        include_default_tools.append("SwitchLLMTool")
    agent = agent.model_copy(update={"include_default_tools": include_default_tools})

    prompt = switch_instruction(task, initial_tier) + "\n\n" + build_task_prompt(task, repo)

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
        tags={"lesson": "p09", "strategy": "cascade-switch", "task": task.id},
        user_id=os.environ.get("P09_TRACE_USER_ID"),
    )

    start = time.time()
    error: str | None = None
    passed = False
    try:
        conversation.send_message(prompt)
        conversation.run()
        check_task(repo, task.id)
        passed = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        wall = time.time() - start

    metrics = conversation.conversation_stats.get_combined_metrics()
    tokens_in, tokens_out = token_counts(metrics)
    events = list(conversation.state.events)
    switch_reasons = extract_switch_reasons(events)
    switched_tiers = [
        PROFILE_TO_TIER.get(reason.split(":", 1)[0], reason.split(":", 1)[0])
        for reason in switch_reasons
    ]
    remote_attempts = count_remote_attempts(events)
    conversation_id = str(conversation.id)
    conversation.close()

    local_in, local_out, local_cost, local_calls = metric_totals([llm])
    attempts = local_calls or remote_attempts
    cost = float(metrics.accumulated_cost or local_cost or 0.0)
    if not tokens_in and local_in:
        tokens_in, tokens_out = local_in, local_out

    print(f"Canvas URL: {args.agent_server.rstrip('/')}/conversations/{conversation_id}")

    return RunResult(
        strategy="cascade",
        task_id=task.id,
        task=task.prompt,
        models_used=[initial_tier] + switched_tiers,
        attempts=attempts,
        escalations=len(switch_reasons),
        escalation_reasons=switch_reasons,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        passed=passed,
        wall_seconds=wall,
        worktree=repo,
        error=error,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the P09 cascade with SwitchLLMTool in Agent Canvas.")
    parser.add_argument("--task", action="append", dest="task_ids", help="Run one task id. May be repeated.")
    parser.add_argument("--all-tasks", action="store_true", help="Run all 10 tasks instead of the default smoke task.")
    parser.add_argument("--agent-server", default=os.environ.get("AGENT_SERVER", "http://127.0.0.1:18000"))
    parser.add_argument("--run-root", default=str(PROJECT_DIR / ".openhands-runs" / "p09"))
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("P09_MAX_ITERATIONS", "40")))
    parser.add_argument("--setup-profiles", action="store_true")
    parser.add_argument("--save-profile-secrets", action="store_true")
    args = parser.parse_args()

    if args.setup_profiles:
        save_profiles(args.save_profile_secrets)

    if args.all_tasks:
        tasks = load_tasks()
    else:
        task_ids = args.task_ids or ["p09-task-08"]
        tasks = [find_task(task_id) for task_id in task_ids]

    results = [run_switch_task(task, args) for task in tasks]
    print_results(results)


if __name__ == "__main__":
    main()
