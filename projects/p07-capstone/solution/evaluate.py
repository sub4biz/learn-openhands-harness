"""P07a evaluator - compare no-critic vs critic runs.

Run a small checkable task repeatedly and print pass-rate/cost-per-pass.

Dry run:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python evaluate.py --dry-run

Live run:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python evaluate.py --trials 5 --config both

Required env vars for live mode: LLM_API_KEY
Optional critic env: CRITIC_SERVER_URL, CRITIC_API_KEY, CRITIC_MODEL_NAME
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECTS_DIR.parent
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr
from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.workspace import DockerWorkspace


DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"
DEFAULT_DOCKER_IMAGE = "ghcr.io/openhands/agent-server:latest-python"

TOOLS = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]

WORDSTATS_RUBRIC = """\
Pass only if all five checks are true:
1. `wordstats/stats.py` exposes `analyze_file(filepath)`.
2. `wordstats/cli.py` runs as `python wordstats/cli.py <file>`.
3. Empty files return zeros.
4. Hyphenated words and contractions count as words; numbers do not.
5. Missing files raise `FileNotFoundError` and the CLI exits non-zero.
"""

WORDSTATS_TASK = f"""\
Create a Python word statistics tool called `wordstats`.

Required files:
- `wordstats/stats.py`
- `wordstats/cli.py`

`stats.py` must define `analyze_file(filepath) -> dict` with exactly these keys:
- `lines`
- `words`
- `chars`
- `unique_words`

Rules:
- `lines` counts newline-separated lines, including empty lines.
- `chars` counts every character, including whitespace.
- Words are alphabetic tokens. Hyphenated words count as one word.
- Contractions like `don't` count as one word.
- Numbers such as `42` and `3.14` are not words.
- Empty files return all zeros.
- Missing files raise `FileNotFoundError` with a clear message.

`cli.py` must run as `python wordstats/cli.py <filepath>`.
It should print one line each for `Lines`, `Words`, `Chars`, and `Unique words`.
It should exit 1 and print an error to stderr when the file is missing.

Rubric:
{WORDSTATS_RUBRIC}
"""

SCORER = r'''
import json
import subprocess
import sys
from pathlib import Path

checks = {
    "files_exist": False,
    "analyze_imports": False,
    "empty_file": False,
    "word_rules": False,
    "missing_file": False,
    "cli": False,
}
errors = []

root = Path.cwd()
stats_path = root / "wordstats" / "stats.py"
cli_path = root / "wordstats" / "cli.py"
checks["files_exist"] = stats_path.exists() and cli_path.exists()

case_dir = root / ".p07_eval_cases"
case_dir.mkdir(exist_ok=True)

try:
    from wordstats.stats import analyze_file
    checks["analyze_imports"] = callable(analyze_file)

    empty = case_dir / "empty.txt"
    empty.write_text("", encoding="utf-8")
    empty_result = analyze_file(str(empty))
    checks["empty_file"] = empty_result == {
        "lines": 0,
        "words": 0,
        "chars": 0,
        "unique_words": 0,
    }

    text = "Well-known words don't include 42 or 3.14.\n"
    sample = case_dir / "sample.txt"
    sample.write_text(text, encoding="utf-8")
    result = analyze_file(str(sample))
    checks["word_rules"] = (
        set(result) == {"lines", "words", "chars", "unique_words"}
        and result["lines"] == 1
        and result["chars"] == len(text)
        and result["words"] == 5
        and result["unique_words"] == 5
    )

    try:
        analyze_file(str(case_dir / "missing.txt"))
    except FileNotFoundError:
        checks["missing_file"] = True

    cli_run = subprocess.run(
        [sys.executable, "wordstats/cli.py", str(sample)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = cli_run.stdout.lower()
    checks["cli"] = (
        cli_run.returncode == 0
        and "lines" in output
        and "words" in output
        and "chars" in output
        and "unique" in output
    )
except Exception as exc:
    errors.append(f"{type(exc).__name__}: {exc}")

score = sum(1 for value in checks.values() if value) / len(checks)
print(json.dumps({"checks": checks, "score": score, "passed": score == 1.0, "errors": errors}))
'''


@dataclass
class TrialResult:
    config: str
    trial: int
    passed: bool
    score: float
    iterations: int
    events: int
    wall: float
    cost: float
    workspace: str
    error: str | None = None


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    print(f"Missing required environment variable: {name}", file=sys.stderr)
    raise SystemExit(2)


def preflight_docker() -> None:
    if not shutil.which("docker"):
        print("Docker is required for P07 evaluation, but `docker` was not found.", file=sys.stderr)
        raise SystemExit(2)
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else "docker info failed"
        print(f"Docker must be running for P07 evaluation: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_critic(api_key: str, args: argparse.Namespace) -> APIBasedCritic:
    iterative = IterativeRefinementConfig(
        success_threshold=args.critic_threshold,
        max_iterations=args.critic_max_iterations,
    )
    return APIBasedCritic(
        server_url=os.environ.get(
            "CRITIC_SERVER_URL",
            "https://llm-proxy.app.all-hands.dev/vllm",
        ),
        api_key=SecretStr(os.environ.get("CRITIC_API_KEY", api_key)),
        model_name=os.environ.get("CRITIC_MODEL_NAME", "critic"),
        iterative_refinement=iterative,
    )


def score_workspace(workspace: Path) -> tuple[bool, float, dict]:
    result = subprocess.run(
        [sys.executable, "-c", SCORER],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return False, 0.0, {
            "checks": {},
            "errors": [result.stderr.strip() or result.stdout.strip()],
        }
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, 0.0, {"checks": {}, "errors": [result.stdout.strip()]}
    return bool(data["passed"]), float(data["score"]), data


def critic_iterations(events) -> int:
    scores = []
    for event in events:
        critic_result = getattr(event, "critic_result", None)
        if critic_result is not None:
            scores.append(float(getattr(critic_result, "score", 0.0)))
    return max(1, len(scores))


def run_trial(config: str, trial: int, args: argparse.Namespace, api_key: str) -> TrialResult:
    run_root = Path(os.environ.get("P07_RUN_ROOT", REPO_ROOT / ".openhands-runs" / "p07-evaluate"))
    run_root.mkdir(parents=True, exist_ok=True)
    workspace_dir = Path(tempfile.mkdtemp(prefix=f"{config}_{trial}_", dir=run_root))
    port = args.port + (trial - 1) + (100 if config == "critic" else 0)

    llm = LLM(
        usage_id=f"agent-{config}",
        model=args.model,
        api_key=SecretStr(api_key),
    )
    critic = build_critic(api_key, args) if config == "critic" else None
    agent = Agent(llm=llm, tools=TOOLS, critic=critic)

    t0 = time.time()
    error = None
    events = []
    cost = 0.0
    try:
        with DockerWorkspace(
            server_image=args.docker_image,
            host_port=port,
            mount_dir=str(workspace_dir),
        ) as workspace:
            conversation = Conversation(agent=agent, workspace=workspace)
            try:
                conversation.send_message(WORDSTATS_TASK)
                conversation.run()
                events = list(conversation.state.events)
                metrics = conversation.conversation_stats.get_combined_metrics()
                cost = float(getattr(metrics, "accumulated_cost", 0.0) or 0.0)
            finally:
                conversation.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    wall = time.time() - t0
    passed, score, details = score_workspace(workspace_dir)
    if error:
        details.setdefault("errors", []).append(error)
    (workspace_dir / "p07_score.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    return TrialResult(
        config=config,
        trial=trial,
        passed=passed,
        score=score,
        iterations=critic_iterations(events),
        events=len(events),
        wall=wall,
        cost=cost,
        workspace=str(workspace_dir),
        error=error,
    )


def summarize(results: list[TrialResult]) -> None:
    print("\nTrial results")
    print("-" * 108)
    print(
        f"{'Config':<10} {'Trial':>5} {'Pass':>6} {'Score':>7} {'Iters':>7} "
        f"{'Events':>7} {'Wall':>8} {'Cost':>10} Workspace"
    )
    print("-" * 108)
    for result in results:
        print(
            f"{result.config:<10} {result.trial:>5} {str(result.passed):>6} "
            f"{result.score:>7.2f} {result.iterations:>7} {result.events:>7} "
            f"{result.wall:>7.1f}s ${result.cost:>9.4f} {result.workspace}"
        )
        if result.error:
            print(f"{'':<10} {'error':>5} {result.error}")

    print("\nSummary")
    print("-" * 72)
    print(f"{'Config':<10} {'Pass rate':>10} {'Median iters':>13} {'Median cost':>12} {'Cost/pass':>12}")
    print("-" * 72)
    for config in sorted({result.config for result in results}):
        rows = [result for result in results if result.config == config]
        passes = sum(1 for result in rows if result.passed)
        pass_rate = passes / len(rows) if rows else 0.0
        total_cost = sum(result.cost for result in rows)
        cost_per_pass = total_cost / passes if passes else float("inf")
        cost_label = "inf" if cost_per_pass == float("inf") else f"${cost_per_pass:.4f}"
        print(
            f"{config:<10} {passes}/{len(rows):<7} "
            f"{statistics.median(result.iterations for result in rows):>13.1f} "
            f"${statistics.median(result.cost for result in rows):>11.4f} "
            f"{cost_label:>12}"
        )
        print(f"{'':<10} pass_rate={pass_rate:.0%}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate P07 critic impact.")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--config", choices=["no-critic", "critic", "both"], default="both")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--port", type=int, default=int(os.environ.get("P07_DOCKER_PORT", "8020")))
    parser.add_argument("--docker-image", default=os.environ.get("P07_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE))
    parser.add_argument("--critic-threshold", type=float, default=float(os.environ.get("CRITIC_SUCCESS_THRESHOLD", "0.7")))
    parser.add_argument("--critic-max-iterations", type=int, default=int(os.environ.get("CRITIC_MAX_ITERATIONS", "3")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score-only", action="append", default=[], metavar="PATH")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials < 1:
        print("--trials must be at least 1", file=sys.stderr)
        raise SystemExit(2)

    if args.score_only:
        results = []
        for index, raw_path in enumerate(args.score_only, start=1):
            workspace = Path(raw_path).expanduser().resolve()
            passed, score, details = score_workspace(workspace)
            (workspace / "p07_score.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
            results.append(
                TrialResult("score-only", index, passed, score, 1, 0, 0.0, 0.0, str(workspace))
            )
        summarize(results)
        return

    configs = ["no-critic", "critic"] if args.config == "both" else [args.config]
    if args.dry_run:
        print("No model calls will be made.")
        print(f"Configs: {', '.join(configs)}")
        print(f"Trials per config: {args.trials}")
        print(f"Docker host ports start at {args.port}; critic trials use +100.")
        print(f"Critic threshold: {args.critic_threshold}")
        print(f"Critic max iterations: {args.critic_max_iterations}")
        print("\nTask prompt:")
        print(WORDSTATS_TASK)
        return

    preflight_docker()
    api_key = require_env("LLM_API_KEY")
    results = []
    for config in configs:
        for trial in range(1, args.trials + 1):
            print(f"\n--- {config} trial {trial}/{args.trials} ---")
            results.append(run_trial(config, trial, args, api_key))

    summarize(results)
    output = REPO_ROOT / ".openhands-runs" / "p07-evaluate" / "results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8")
    print(f"\nSaved results: {output}")


if __name__ == "__main__":
    main()
