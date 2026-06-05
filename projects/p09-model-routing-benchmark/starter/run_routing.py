"""P09 starter: model routing as harness engineering.

Run the dry route table first:
    uv run --with openhands-sdk --with openhands-tools --with pytest python run_routing.py --dry-run

Then fill the TODOs and run one live rules task:
    LLM_API_KEY=... uv run --with openhands-sdk --with openhands-tools --with pytest python run_routing.py --task p09-task-06
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = PROJECT_DIR.parents[0]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from _runtime import load_dotenv, token_counts

load_dotenv(PROJECT_DIR)

from observability import configure_p09_observability

configure_p09_observability()

from check_task import check_task
from openhands.sdk import Conversation, LLM
from openhands.sdk.llm import Message, RouterLLM
from openhands.tools.preset.default import get_default_agent

Tier = Literal["cheap", "mid", "frontier"]

DEFAULT_MODELS: dict[Tier, str] = {
    "cheap": "anthropic/claude-haiku-4-5-20251001",
    "mid": "anthropic/claude-sonnet-4-6",
    "frontier": "anthropic/claude-opus-4-8",
}
TIER_TURN_BUDGETS: dict[Tier, int] = {"cheap": 8, "mid": 14, "frontier": 20}
CHEAP_HARD_TURN_BUDGET = 1


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    difficulty: str
    tags: list[str]
    paths: list[str]
    success_check: str


class StaticRulesRouter(RouterLLM):
    """TODO: implement the first routing policy with RouterLLM."""

    task_id: str = ""
    task_prompt: str = ""
    task_difficulty: str = ""
    task_tags: list[str] = Field(default_factory=list)
    task_paths: list[str] = Field(default_factory=list)
    selected_tier: Tier | None = None
    route_history: list[str] = Field(default_factory=list)

    def select_llm(self, messages: list[Message]) -> str:
        # TODO:
        # 1. Rebuild the Task metadata and call route_by_rules(...) the first
        #    time this method runs.
        # 2. Store the tier in selected_tier.
        # 3. Keep returning that same tier for the rest of the conversation.
        # The cascade is a separate exercise because it uses SwitchLLMTool and
        # OpenHands profiles to change models during the run.
        tier = self.selected_tier or "cheap"
        self.route_history.append(tier)
        return tier


def load_tasks() -> list[Task]:
    return [Task(**item) for item in json.loads((PROJECT_DIR / "tasks.json").read_text())]


def approximate_tokens(text: str) -> int:
    return len(text.split())


def route_by_rules(task: Task) -> Tier:
    # TODO: implement Layer 0 risk floor:
    # if task touches auth/security paths or tags, return "frontier".
    if approximate_tokens(task.prompt) < 200 and "```" not in task.prompt:
        return "cheap"
    if task.difficulty == "hard":
        return "frontier"
    return "mid"


def turn_budget_for(task: Task, tier: Tier) -> int:
    if tier == "cheap" and task.difficulty == "hard":
        return CHEAP_HARD_TURN_BUDGET
    return TIER_TURN_BUDGETS[tier]


def build_llms() -> dict[Tier, LLM]:
    api_key = os.environ.get("LLM_API_KEY")
    secret = SecretStr(api_key) if api_key else None
    return {
        tier: LLM(
            model=os.environ.get(f"P09_MODEL_{tier.upper()}", model),
            api_key=secret,
            base_url=os.environ.get("LLM_BASE_URL"),
            usage_id=f"p09-{tier}",
        )
        for tier, model in DEFAULT_MODELS.items()
    }


def prepare_repo(task: Task, strategy: str) -> Path:
    dest = PROJECT_DIR / ".openhands-runs" / "p09-starter" / strategy / task.id
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECT_DIR / "toy_repo", dest)
    return dest


def build_prompt(task: Task, repo: Path) -> str:
    check_command = task.success_check.format(
        repo=str(repo),
        checker=str(PROJECT_DIR / "check_task.py"),
    )
    return (
        f"{task.prompt}\n\n"
        "Use the task prompt as the specification. Treat the check command as a "
        "validator, not as the starting spec; inspect check_task.py only if a "
        "check failure is ambiguous. Run only this task-specific check. When it "
        f"prints `{task.id}: PASS`, stop immediately and summarize the change.\n\n"
        f"Run this check before finishing:\n{check_command}"
    )


def run_task(task: Task, strategy: str, dry_run: bool) -> dict[str, object]:
    llms = build_llms()
    if strategy == "frontier":
        tier = "frontier"
        llm = llms[tier]
        max_iterations = 30
    elif strategy == "static":
        tier = route_by_rules(task)
        llm = StaticRulesRouter(
            router_name=f"starter-static-router-{task.id}",
            llms_for_routing=llms,
            task_id=task.id,
            task_prompt=task.prompt,
            task_difficulty=task.difficulty,
            task_tags=task.tags,
            task_paths=task.paths,
            selected_tier=tier,
        )
        max_iterations = turn_budget_for(task, tier)
    else:
        raise SystemExit(
            "Cascade uses SwitchLLMTool and OpenHands profiles. "
            "Use starter/run_switch_cascade.py for that exercise."
        )

    if dry_run:
        return {"task": task.id, "strategy": strategy, "models": tier, "passed": False, "cost": 0.0}

    repo = prepare_repo(task, strategy)
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(agent=agent, workspace=str(repo), max_iteration_per_run=max_iterations)
    try:
        conversation.send_message(build_prompt(task, repo))
        conversation.run()
        check_task(repo, task.id)
        passed = True
    except Exception:
        passed = False
    finally:
        metrics = conversation.conversation_stats.get_combined_metrics()
        conversation.close()

    tokens_in, tokens_out = token_counts(metrics)
    return {
        "task": task.id,
        "strategy": strategy,
        "models": "TODO",
        "passed": passed,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": metrics.accumulated_cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["frontier", "static", "all"], default="all")
    parser.add_argument("--task", action="append", dest="task_ids")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tasks = load_tasks()
    if args.task_ids:
        wanted = set(args.task_ids)
        tasks = [task for task in tasks if task.id in wanted]

    strategies = ["frontier", "static"] if args.strategy == "all" else [args.strategy]
    results = [run_task(task, strategy, args.dry_run) for strategy in strategies for task in tasks]

    for result in results:
        print(result)
    print("TODO: print totals, pass count, and cost per solved task.")


if __name__ == "__main__":
    main()
