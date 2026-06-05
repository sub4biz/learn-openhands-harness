from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
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
from openhands.sdk.llm import Message, RouterLLM, TextContent
from openhands.tools.preset.default import get_default_agent

Tier = Literal["cheap", "mid", "frontier"]
Strategy = Literal["frontier", "static", "cascade"]

DEFAULT_MODELS: dict[Tier, str] = {
    "cheap": "anthropic/claude-haiku-4-5-20251001",
    "mid": "anthropic/claude-sonnet-4-6",
    "frontier": "anthropic/claude-opus-4-8",
}
RISK_TAGS = {"security", "auth", "high-risk"}
TIER_ORDER: list[Tier] = ["cheap", "mid", "frontier"]
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


@dataclass
class RunResult:
    strategy: str
    task_id: str
    task: str
    models_used: list[str]
    attempts: int
    escalations: int
    escalation_reasons: list[str]
    tokens_in: int
    tokens_out: int
    cost: float
    passed: bool
    wall_seconds: float
    worktree: Path
    error: str | None = None


@dataclass
class JudgeVerdict:
    escalate: bool
    target: Tier
    reason: str
    confidence: float


def load_tasks(path: Path = PROJECT_DIR / "tasks.json") -> list[Task]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Task(**item) for item in payload]


def selected_tasks(task_ids: list[str] | None) -> list[Task]:
    tasks = load_tasks()
    if not task_ids:
        return tasks
    wanted = set(task_ids)
    unknown = wanted - {task.id for task in tasks}
    if unknown:
        raise SystemExit(f"unknown task ids: {', '.join(sorted(unknown))}")
    return [task for task in tasks if task.id in wanted]


def prompt_tokens(text: str) -> int:
    return len(re.findall(r"\S+", text))


def risk_floor(task: Task) -> bool:
    tags = {tag.lower() for tag in task.tags}
    if tags & RISK_TAGS:
        return True
    return any("auth" in path.lower() or "security" in path.lower() for path in task.paths)


def rules_route(task: Task) -> Tier:
    if risk_floor(task):
        return "frontier"
    if prompt_tokens(task.prompt) < 200 and "```" not in task.prompt:
        return "cheap"
    if task.difficulty == "hard":
        return "frontier"
    return "mid"


def next_tier(current: Tier) -> Tier:
    index = TIER_ORDER.index(current)
    return TIER_ORDER[min(index + 1, len(TIER_ORDER) - 1)]


def turn_budget_for(task: Task, tier: Tier) -> int:
    if tier == "cheap" and task.difficulty == "hard":
        return CHEAP_HARD_TURN_BUDGET
    return TIER_TURN_BUDGETS[tier]


def llm_message_text(message: object) -> str:
    content = getattr(message, "content", None)
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
            elif isinstance(item, dict) and item.get("text") is not None:
                parts.append(str(item["text"]))
    elif isinstance(content, str):
        parts.append(content)

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        parts.append(str(tool_calls))

    if parts:
        return "\n".join(parts)

    try:
        return json.dumps(message.model_dump(mode="json"), sort_keys=True)
    except Exception:
        return str(message)


def messages_text(messages: list[Message]) -> str:
    return "\n".join(llm_message_text(message) for message in messages)


def tail_text(messages: list[Message], count: int = 6) -> str:
    return messages_text(messages[-count:])


def extract_error_fingerprints(text: str) -> list[str]:
    fingerprints: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "AssertionError" in stripped:
            fingerprints.append(stripped[-180:])
        elif stripped.startswith("FAILED "):
            fingerprints.append(stripped[-180:])
        elif stripped.startswith("E   "):
            fingerprints.append(stripped[-180:])
        elif "Traceback (most recent call last)" in stripped:
            fingerprints.append("Traceback")
    return fingerprints


def extract_test_failures(text: str) -> list[str]:
    failures = re.findall(r"FAILED\s+([^\s]+)", text)
    node_ids = re.findall(r"([A-Za-z0-9_./-]+\.py::[A-Za-z0-9_:\[\]-]+)", text)
    return failures + node_ids


def extract_changed_files(text: str) -> list[str]:
    suffix = r"(?:py|md|toml|txt|json|yaml|yml)"
    patterns = [
        rf"\[File\s+([^\]\n]+?\.{suffix})\s+edited with",
        rf"(?:Updated|Modified|Edited|Created|Wrote)\s+file:?\s+([A-Za-z0-9_./-]+\.{suffix})",
        rf"command['\"]?\s*[:=]\s*['\"](?:create|str_replace|insert|undo_edit)['\"].{{0,500}}?"
        rf"path['\"]?\s*[:=]\s*['\"]([^'\"]+\.{suffix})",
    ]
    files: list[str] = []
    for pattern in patterns:
        files.extend(re.findall(pattern, text, flags=re.DOTALL))
    return files


def extract_actions(messages: list[Message], count: int = 3) -> list[str]:
    actions: list[str] = []
    for message in messages[-8:]:
        text = llm_message_text(message)
        if "terminal" in text or "bash" in text:
            actions.append("terminal command")
        elif "file_editor" in text:
            actions.append("file edit")
        elif "pytest" in text:
            actions.append("pytest")
        elif text.strip():
            actions.append(text.strip().splitlines()[0][:90])
    return actions[-count:]


def task_passed_in_text(task_id: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(task_id)}:\s*PASS\b", text))


class StaticRulesRouter(RouterLLM):
    """Route once from task metadata, then keep returning the same tier."""

    task_id: str = ""
    task_prompt: str = ""
    task_difficulty: str = ""
    task_tags: list[str] = Field(default_factory=list)
    task_paths: list[str] = Field(default_factory=list)
    selected_tier: Tier | None = None
    route_history: list[str] = Field(default_factory=list)

    def select_llm(self, messages: list[Message]) -> str:
        if self.selected_tier is None:
            task = Task(
                id=self.task_id,
                prompt=self.task_prompt,
                difficulty=self.task_difficulty,
                tags=self.task_tags,
                paths=self.task_paths,
                success_check="",
            )
            self.selected_tier = rules_route(task)
        self.route_history.append(self.selected_tier)
        return self.selected_tier


class EscalatingRouter(RouterLLM):
    task_id: str = ""
    task_prompt: str = ""
    task_difficulty: str = ""
    task_tags: list[str] = Field(default_factory=list)
    task_paths: list[str] = Field(default_factory=list)
    tier: Tier = "cheap"
    judge_llm: LLM | None = None
    judge_mode: Literal["llm", "heuristic"] = "llm"
    max_escalations: int = 2
    hysteresis_turns: int = 3
    turn_budget_by_tier: dict[str, int] = Field(
        default_factory=lambda: dict(TIER_TURN_BUDGETS)
    )
    force_mid_after_first_call: bool = False
    call_count: int = 0
    processed_message_count: int = 0
    last_escalation_turn: int = -999
    task_completed: bool = False
    escalations_log: list[dict[str, object]] = Field(default_factory=list)
    route_history: list[str] = Field(default_factory=list)
    seen_error_fingerprints: dict[str, int] = Field(default_factory=dict)
    seen_test_failures: dict[str, int] = Field(default_factory=dict)
    seen_file_edits: dict[str, int] = Field(default_factory=dict)
    last_diff_hash: str | None = None
    unchanged_diff_turns: int = 0

    def select_llm(self, messages: list[Message]) -> str:
        self.call_count += 1
        task = Task(
            id=self.task_id,
            prompt=self.task_prompt,
            difficulty=self.task_difficulty,
            tags=self.task_tags,
            paths=self.task_paths,
            success_check="",
        )

        if risk_floor(task):
            self.tier = "frontier"
            self.route_history.append(self.tier)
            return self.tier

        if (
            self.force_mid_after_first_call
            and self.tier == "cheap"
            and self.route_history
            and self._can_escalate()
        ):
            reason = (
                "Escalating: hard task reached the one-call cheap trust budget; "
                "moving to mid before continuing implementation"
            )
            self.escalations_log.append(
                {
                    "turn": self.call_count,
                    "from": self.tier,
                    "to": "mid",
                    "reason": reason,
                    "confidence": 1.0,
                    "triggers": ["hard task one-call cheap trust budget"],
                }
            )
            self.tier = "mid"
            self.last_escalation_turn = self.call_count

        triggers = self._triggers_fired(messages)
        if self.task_completed:
            self.route_history.append(self.tier)
            return self.tier

        if triggers and self._can_escalate():
            summary = self._condense(messages, triggers)
            verdict = self._judge(summary, triggers)
            if verdict.escalate:
                target = verdict.target
                if TIER_ORDER.index(target) <= TIER_ORDER.index(self.tier):
                    target = next_tier(self.tier)
                if target != self.tier:
                    self.escalations_log.append(
                        {
                            "turn": self.call_count,
                            "from": self.tier,
                            "to": target,
                            "reason": verdict.reason,
                            "confidence": verdict.confidence,
                            "triggers": triggers,
                        }
                    )
                    self.tier = target
                    self.last_escalation_turn = self.call_count

        self.route_history.append(self.tier)
        return self.tier

    def _can_escalate(self) -> bool:
        if self.tier == "frontier":
            return False
        if len(self.escalations_log) >= self.max_escalations:
            return False
        return self.call_count - self.last_escalation_turn >= self.hysteresis_turns

    def _triggers_fired(self, messages: list[Message]) -> list[str]:
        new_messages = messages[self.processed_message_count :]
        self.processed_message_count = len(messages)
        text = messages_text(new_messages) if new_messages else ""
        context_text = tail_text(messages)
        triggers: list[str] = []

        if text:
            if task_passed_in_text(self.task_id, text):
                self.task_completed = True
                return []

            for failure in set(extract_test_failures(text)):
                count = self.seen_test_failures.get(failure, 0) + 1
                self.seen_test_failures[failure] = count
                if count >= 2:
                    triggers.append(f"same test failing twice: {failure}")

            for fingerprint in set(extract_error_fingerprints(text)):
                count = self.seen_error_fingerprints.get(fingerprint, 0) + 1
                self.seen_error_fingerprints[fingerprint] = count
                if count >= 2:
                    triggers.append(f"repeated error: {fingerprint}")

            for file_path in set(extract_changed_files(text)):
                count = self.seen_file_edits.get(file_path, 0) + 1
                self.seen_file_edits[file_path] = count
                if count >= 3:
                    triggers.append(f"same file changed {count} times: {file_path}")

        budget = self._turn_budget()
        if self.call_count > budget:
            triggers.append(f"turn budget exceeded for {self.tier}: {self.call_count}>{budget}")

        if "diff --git" in context_text:
            diff_hash = str(hash(context_text[context_text.find("diff --git") :]))
            if diff_hash == self.last_diff_hash:
                self.unchanged_diff_turns += 1
            else:
                self.unchanged_diff_turns = 0
                self.last_diff_hash = diff_hash
            if self.unchanged_diff_turns >= 2:
                triggers.append("diff unchanged for 2 turns")

        return sorted(set(triggers))

    def _turn_budget(self) -> int:
        if self.tier == "cheap" and self.task_difficulty == "hard":
            return CHEAP_HARD_TURN_BUDGET
        return self.turn_budget_by_tier.get(self.tier, 8)

    def _condense(self, messages: list[Message], triggers: list[str]) -> dict[str, object]:
        text = tail_text(messages)
        errors = extract_error_fingerprints(text)[-2:]
        failures = extract_test_failures(text)[-2:]
        test_status = "failing" if errors or failures else "unknown"
        return {
            "task": self.task_prompt,
            "task_id": self.task_id,
            "current_model_tier": self.tier,
            "last_3_actions": extract_actions(messages),
            "last_2_errors": errors or failures,
            "test_status": test_status,
            "triggers": triggers,
        }

    def _judge(self, summary: dict[str, object], triggers: list[str]) -> JudgeVerdict:
        if self.judge_mode == "heuristic" or self.judge_llm is None:
            return self._heuristic_judge(triggers)

        prompt = (
            "You are the escalation judge for a coding-agent model router.\n"
            "Escalate only when the evidence shows the current model is stuck.\n"
            "Do not escalate just because the model viewed files or made one normal edit.\n"
            "If the only evidence is same-file changes with no failing test or repeated error, "
            "return escalate=false for routine tasks.\n"
            "Return only JSON with keys: escalate, target, reason, confidence.\n"
            "target must be mid or frontier. The reason must cite specific evidence.\n\n"
            f"State summary:\n{json.dumps(summary, indent=2)}"
        )
        try:
            response = self.judge_llm.completion(
                messages=[
                    Message(
                        role="user",
                        content=[TextContent(text=prompt)],
                    )
                ]
            )
            raw = llm_message_text(response.message)
            payload = json.loads(_extract_json_object(raw))
            target = payload.get("target", next_tier(self.tier))
            if target not in {"mid", "frontier"}:
                target = next_tier(self.tier)
            return JudgeVerdict(
                escalate=bool(payload.get("escalate", False)),
                target=target,
                reason=str(payload.get("reason", "; ".join(triggers))),
                confidence=float(payload.get("confidence", 0.5)),
            )
        except Exception as exc:
            fallback = self._heuristic_judge(triggers)
            fallback.reason = f"{fallback.reason}; judge fallback after {type(exc).__name__}"
            fallback.confidence = min(fallback.confidence, 0.55)
            return fallback

    def _heuristic_judge(self, triggers: list[str]) -> JudgeVerdict:
        target = next_tier(self.tier)
        reason = "Escalating: " + "; ".join(triggers[:2])
        return JudgeVerdict(
            escalate=True,
            target=target,
            reason=reason,
            confidence=0.72,
        )


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


def model_for_tier(tier: Tier) -> str:
    return os.environ.get(f"P09_MODEL_{tier.upper()}", DEFAULT_MODELS[tier])


def build_llms(api_key: str | None, base_url: str | None = None) -> dict[Tier, LLM]:
    secret = SecretStr(api_key) if api_key else None
    return {
        tier: LLM(
            model=model_for_tier(tier),
            api_key=secret,
            base_url=base_url or os.environ.get("LLM_BASE_URL"),
            usage_id=f"p09-{tier}",
        )
        for tier in DEFAULT_MODELS
    }


def build_judge_llm(api_key: str | None, base_url: str | None = None) -> LLM:
    secret = SecretStr(api_key) if api_key else None
    return LLM(
        model=os.environ.get("P09_JUDGE_MODEL", DEFAULT_MODELS["cheap"]),
        api_key=secret,
        base_url=base_url or os.environ.get("LLM_BASE_URL"),
        usage_id="p09-judge",
    )


def print_model_config() -> None:
    print("P09 model configuration:")
    for tier in TIER_ORDER:
        env_name = f"P09_MODEL_{tier.upper()}"
        source = env_name if os.environ.get(env_name) else "default"
        print(f"  {tier:<8} {model_for_tier(tier)} ({source})")
    judge_source = "P09_JUDGE_MODEL" if os.environ.get("P09_JUDGE_MODEL") else "default cheap"
    print(f"  judge    {os.environ.get('P09_JUDGE_MODEL', DEFAULT_MODELS['cheap'])} ({judge_source})")
    if os.environ.get("LLM_BASE_URL"):
        print("  base_url set via LLM_BASE_URL")


def preflight_models() -> None:
    api_key = os.environ.get("LLM_API_KEY")
    llms = build_llms(api_key)
    judge = build_judge_llm(api_key)
    checks: list[tuple[str, LLM]] = [(tier, llm) for tier, llm in llms.items()]
    checks.append(("judge", judge))
    print_model_config()
    for label, llm in checks:
        try:
            llm.completion(
                messages=[Message(role="user", content=[TextContent(text="Reply with OK.")])]
            )
            metrics = llm.metrics.get_snapshot()
            tokens_in, tokens_out = token_counts(metrics)
            print(f"  {label:<8} OK tokens={tokens_in + tokens_out} cost=${float(metrics.accumulated_cost or 0.0):.6f}")
        except Exception as exc:
            print(f"  {label:<8} FAIL {type(exc).__name__}: {exc}")
            raise


def clean_copy_repo(task: Task, strategy: str, run_root: Path) -> Path:
    destination = run_root / strategy / task.id
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        PROJECT_DIR / "toy_repo",
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    return destination


def build_task_prompt(task: Task, repo: Path, include_check_command: bool) -> str:
    check_command = task.success_check.format(
        repo=str(repo),
        checker=str(PROJECT_DIR / "check_task.py"),
    )
    prompt = (
        f"Task id: {task.id}\n"
        f"Difficulty: {task.difficulty}\n"
        f"Relevant paths: {', '.join(task.paths)}\n\n"
        f"{task.prompt}\n\n"
        "Work in the current repository only. Keep the change scoped to the task. "
        "Use the task prompt as the specification. "
    )
    if not include_check_command:
        return (
            prompt
            + "Do not inspect benchmark validator files. The harness will run "
            "an external success check after you finish. When you believe the "
            "task is complete, stop and summarize the change. Do not run the "
            "full test suite; unrelated task tests are intentionally red. If "
            "you verify locally, use a focused smoke check for this task and "
            "remove any temporary files before finishing."
        )
    return (
        prompt
        + "Treat the check command as a validator, not as the starting spec; "
        "inspect check_task.py only if a check failure is ambiguous. "
        "When you think the task is complete, run this check command and fix any "
        "failures before finishing. Run only this task-specific check. When it "
        f"prints `{task.id}: PASS`, stop immediately and summarize the change:\n\n"
        f"{check_command}"
    )


def metric_totals(llms: list[LLM]) -> tuple[int, int, float, int]:
    total_in = 0
    total_out = 0
    total_cost = 0.0
    calls = 0
    for llm in llms:
        metrics = llm.metrics.get_snapshot()
        prompt, completion = token_counts(metrics)
        total_in += prompt
        total_out += completion
        total_cost += float(metrics.accumulated_cost or 0.0)
        calls += len(getattr(llm.metrics, "token_usages", []) or [])
    return total_in, total_out, total_cost, calls


def run_local_task(
    task: Task,
    strategy: Strategy,
    run_root: Path,
    max_iterations: int,
    judge_mode: Literal["llm", "heuristic"],
    include_check_command: bool,
) -> RunResult:
    api_key = os.environ.get("LLM_API_KEY")
    llms = build_llms(api_key)
    judge_llm = build_judge_llm(api_key)
    repo = clean_copy_repo(task, strategy, run_root)

    if strategy == "frontier":
        agent_llm: LLM = llms["frontier"]
        planned_models = ["frontier"]
        conversation_iterations = max_iterations
    elif strategy == "static":
        tier = rules_route(task)
        agent_llm = StaticRulesRouter(
            router_name=f"p09-static-router-{task.id}",
            llms_for_routing=llms,
            task_id=task.id,
            task_prompt=task.prompt,
            task_difficulty=task.difficulty,
            task_tags=task.tags,
            task_paths=task.paths,
            selected_tier=tier,
        )
        planned_models = [tier]
        conversation_iterations = min(max_iterations, turn_budget_for(task, tier))
    else:
        initial_tier = rules_route(task)
        turn_budgets = dict(TIER_TURN_BUDGETS)
        if initial_tier == "cheap" and task.difficulty == "hard":
            turn_budgets["cheap"] = CHEAP_HARD_TURN_BUDGET
        router = EscalatingRouter(
            router_name=f"p09-router-{task.id}",
            llms_for_routing=llms,
            task_id=task.id,
            task_prompt=task.prompt,
            task_difficulty=task.difficulty,
            task_tags=task.tags,
            task_paths=task.paths,
            tier=initial_tier,
            judge_llm=judge_llm,
            judge_mode=judge_mode,
            turn_budget_by_tier=turn_budgets,
            force_mid_after_first_call=(
                initial_tier == "cheap" and task.difficulty == "hard"
            ),
        )
        agent_llm = router
        planned_models = [initial_tier]
        conversation_iterations = max_iterations

    prompt = build_task_prompt(task, repo, include_check_command)
    agent = get_default_agent(llm=agent_llm, cli_mode=True)
    conversation = Conversation(
        agent=agent,
        workspace=str(repo),
        max_iteration_per_run=conversation_iterations,
        stuck_detection=True,
        tags={"lesson": "p09", "strategy": strategy, "task": task.id},
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
        conversation.close()

    all_llms = list(llms.values())
    if strategy == "cascade":
        all_llms.append(judge_llm)
    tokens_in, tokens_out, cost, calls = metric_totals(all_llms)

    escalation_reasons: list[str] = []
    escalations = 0
    models_used = planned_models
    if strategy == "static":
        router_obj = agent_llm
        assert isinstance(router_obj, StaticRulesRouter)
        models_used = list(dict.fromkeys(router_obj.route_history)) or planned_models
    if strategy == "cascade":
        router_obj = agent_llm
        assert isinstance(router_obj, EscalatingRouter)
        escalations = len(router_obj.escalations_log)
        escalation_reasons = [str(item["reason"]) for item in router_obj.escalations_log]
        models_used = list(dict.fromkeys(router_obj.route_history)) or planned_models

    return RunResult(
        strategy=strategy,
        task_id=task.id,
        task=task.prompt,
        models_used=models_used,
        attempts=calls,
        escalations=escalations,
        escalation_reasons=escalation_reasons,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        passed=passed,
        wall_seconds=wall,
        worktree=repo,
        error=error,
    )


def run_strategy(
    strategy: Strategy,
    tasks: list[Task],
    run_root: Path,
    max_iterations: int,
    judge_mode: Literal["llm", "heuristic"],
    dry_run: bool = False,
    include_check_command: bool = True,
) -> list[RunResult]:
    results: list[RunResult] = []
    for task in tasks:
        route = "frontier" if strategy == "frontier" else rules_route(task)
        if dry_run:
            results.append(
                RunResult(
                    strategy=strategy,
                    task_id=task.id,
                    task=task.prompt,
                    models_used=[route],
                    attempts=0,
                    escalations=0,
                    escalation_reasons=[],
                    tokens_in=0,
                    tokens_out=0,
                    cost=0.0,
                    passed=False,
                    wall_seconds=0.0,
                    worktree=run_root / strategy / task.id,
                    error="dry run",
                )
            )
            continue
        print(f"\n[{strategy}] {task.id}: route={route} difficulty={task.difficulty}")
        results.append(
            run_local_task(
                task,
                strategy,
                run_root,
                max_iterations,
                judge_mode,
                include_check_command,
            )
        )
        latest = results[-1]
        status = "PASS" if latest.passed else "FAIL"
        print(
            f"{status} models={','.join(latest.models_used)} "
            f"calls={latest.attempts} cost=${latest.cost:.4f}"
        )
        for reason in latest.escalation_reasons:
            print(f"  {reason}")
    return results


def print_results(results: list[RunResult]) -> None:
    if not results:
        return
    strategy = results[0].strategy
    print("\n" + "=" * 132)
    print(f"Strategy: {strategy}")
    print(
        f"{'Task':<12} {'Models':<22} {'Calls':>5} {'Esc':>3} "
        f"{'Tokens in':>10} {'Tokens out':>10} {'Cost':>10} {'Pass':>6}"
    )
    print("-" * 132)
    for result in results:
        models = "->".join(result.models_used)
        passed = "dry" if result.error == "dry run" else ("yes" if result.passed else "no")
        print(
            f"{result.task_id:<12} {models:<22} {result.attempts:>5} "
            f"{result.escalations:>3} {result.tokens_in:>10} "
            f"{result.tokens_out:>10} ${result.cost:>9.4f} {passed:>6}"
        )
        if result.escalation_reasons:
            for reason in result.escalation_reasons:
                print(f"  Escalating: {reason}")
        if result.error and result.error != "dry run":
            print(f"  Error: {result.error}")
    print("-" * 132)
    if all(result.error == "dry run" for result in results):
        print("Dry run: routes only. No LLM calls, costs, or pass/fail results.")
        print("=" * 132)
        return

    passed_count = sum(1 for result in results if result.passed)
    total_cost = sum(result.cost for result in results)
    solved_cost = total_cost / passed_count if passed_count else float("inf")
    print(
        f"Summary: passed={passed_count}/{len(results)} "
        f"total_cost=${total_cost:.4f} "
        f"cost_per_solved_task=${solved_cost:.4f}"
    )
    print("=" * 132)


def write_results(path: Path, results: list[RunResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "strategy": result.strategy,
            "task_id": result.task_id,
            "models_used": result.models_used,
            "attempts": result.attempts,
            "escalations": result.escalations,
            "escalation_reasons": result.escalation_reasons,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost": result.cost,
            "passed": result.passed,
            "wall_seconds": result.wall_seconds,
            "worktree": str(result.worktree),
            "error": result.error,
        }
        for result in results
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser(default_strategy: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the P09 model routing lesson.")
    choices = ["frontier", "static", "cascade", "all"] if default_strategy is None else [default_strategy]
    parser.add_argument("--strategy", choices=choices, default=default_strategy or "all")
    parser.add_argument("--task", action="append", dest="task_ids", help="Run one task id. May be repeated.")
    parser.add_argument("--run-root", default=str(PROJECT_DIR / ".openhands-runs" / "p09"))
    parser.add_argument("--max-iterations", type=int, default=int(os.environ.get("P09_MAX_ITERATIONS", "40")))
    parser.add_argument(
        "--judge",
        choices=["llm", "heuristic"],
        default=os.environ.get("P09_JUDGE", "llm"),
        help="Use a real cheap-model judge or the deterministic fallback.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print routes without calling an LLM.")
    parser.add_argument(
        "--opaque-checks",
        action="store_true",
        default=os.environ.get("P09_OPAQUE_CHECKS") == "1",
        help="Do not include the validator command in the agent prompt.",
    )
    parser.add_argument("--json-out", default="")
    parser.add_argument("--print-models", action="store_true", help="Print resolved tier models and exit.")
    parser.add_argument("--preflight-models", action="store_true", help="Call each configured tier once and exit.")
    return parser


def main(default_strategy: str | None = None) -> None:
    parser = build_parser(default_strategy)
    args = parser.parse_args()
    if args.print_models:
        print_model_config()
        return
    if args.preflight_models:
        preflight_models()
        return

    tasks = selected_tasks(args.task_ids)
    run_root = Path(args.run_root).expanduser().resolve()

    strategies: list[Strategy]
    if args.strategy == "all":
        strategies = ["frontier", "static", "cascade"]
    else:
        strategies = [args.strategy]

    all_results: list[RunResult] = []
    for strategy in strategies:
        results = run_strategy(
            strategy,
            tasks,
            run_root=run_root,
            max_iterations=args.max_iterations,
            judge_mode=args.judge,
            dry_run=args.dry_run,
            include_check_command=not args.opaque_checks,
        )
        print_results(results)
        all_results.extend(results)

    if args.json_out:
        write_results(Path(args.json_out).expanduser().resolve(), all_results)


if __name__ == "__main__":
    main()
