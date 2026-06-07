# P04: Task Decomposition

## What Problem Are You Solving?

Some tasks are hard because the model is weak. Others are hard because the harness hands the model too much work in one prompt. This lesson tests that distinction directly, following the "trust your harness" pattern: hold the model mostly constant, change the wrapper, and measure whether smaller scoped calls beat one long call.

You run the same goal two ways:

1. **Monolithic.** One agent run gets the whole task.
2. **Decomposed.** The harness runs scoped checks first, then a final summarizer reads those check files and produces the same deliverable.

Then you compare correctness, cost, wall time, and failure modes. Decomposition is not automatically better; it can lose cross-context information and increase spend. The point is to make the tradeoff measurable.

## Start With These Files

Open this README and `starter/` only. Ask your coding agent to complete the TODOs without reading `solution/`, run the dry run and one live run, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| Run monolithic vs decomposed | `starter/run_decomposition.py` (monolith + TODOs) | `solution/run_decomposition.py` (both, on copied workspaces) |
| Score saved reports offline | | `solution/score_report.py` |
| Artifacts to keep | | `solution/decomposition_plan.md`, `solution/evaluation_rubric.md` |

## The Task And The Two Configs

Hold the model and retrieval policy from P01 to P03 constant, and use the same source repo (a scratch clone; the script copies the workspace before each run, but the agent still has filesystem tools).

> Review this repo for release readiness and produce `RELEASE_READINESS.md` covering docs accuracy, setup/test commands, secret handling, safety warnings, project structure, and concrete fixes.

Config A gives that whole task to one run. Config B runs scoped checks first, then a final summarizer reads those check files and produces the same `RELEASE_READINESS.md`.

Before you run, predict. Which parts of the task are independent enough to split? What rubric categories might the monolithic run miss? How much extra cost or wall time would decomposition need to justify itself? What aggregation failure would make the decomposed run worse?

## Run It And Collect Metrics

From the solution directory, dry-run the plan without paid calls:

```bash
WORKSPACE_DIR=/path/to/repo \
uv run --with openhands-sdk --with openhands-tools python run_decomposition.py --dry-run
```

Then run live with the agent server up:

```bash
WORKSPACE_DIR=/path/to/repo \
uv run --with openhands-sdk --with openhands-tools python run_decomposition.py
```

The cap is `P04_MAX_ITERATIONS=60` per run. If the monolithic run hits it, the script writes `MONOLITH_TRUNCATED.md` and continues; treat that as a result ("the one-prompt version could not finish under this budget"). Use `--mode decomposed` to run one side while debugging, and `--resume-dir <copied-workspace>` to resume an interrupted decomposed run.

If your agent server is Dockerized, pass the path mapping so the `/projects` mount resolves:

```bash
AGENT_WORKSPACE_HOST_ROOT=/path/to/your/projects \
AGENT_WORKSPACE_SERVER_ROOT=/projects \
WORKSPACE_DIR=/path/to/your/projects/learn-openhands-harness \
uv run --with openhands-sdk --with openhands-tools python run_decomposition.py
```

The runner prints a rubric scorecard after live runs. To score saved reports later without model calls:

```bash
uv run python projects/p04-decomposition/solution/score_report.py \
  --score-report monolith=<path>/RELEASE_READINESS.md \
  --score-report decomposed=<path>/RELEASE_READINESS.md
```

Copied workspaces live under `.openhands-runs/p04-decomposition/` (gitignored).

## Record The Results

| Run | Completed under budget? | Rubric coverage | Wall | Cost | Counts match tables? |
|---|:--:|---:|---:|---:|:--:|
| monolith | | | | | |
| decomposed | | | | | |

## How To Read The Results

- Did the monolithic run complete but miss expected blocker categories?
- Did the decomposed run improve rubric coverage, or just produce more files?
- Did a scoped check fail without killing the whole review?
- Did the final aggregator preserve caveats and exact file paths from the scoped checks, and do its declared issue counts match its issue tables?
- Was the extra cost worth the gain?

Decomposition wins when a task has independent dimensions, a clear aggregation format, and failures you can retry in isolation. It loses when the subparts need tight shared context.

<details>
<summary>References</summary>

- [Harvey legal agent benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-initial-results): the "trust your harness" framing of scoped calls vs one long call.
- [P07: Critic Capstone](../p07-capstone/): where you reuse this judgment to decide on a critic or subagent.

</details>

## What Students Should Leave With

A decomposition rule of thumb, for example:

> Break a task into scoped runs when it has independent review dimensions, a clear aggregation format, and failures that can be retried independently. Keep it monolithic when the subparts require tight shared context.

Save your version in `solution/decomposition_plan.md`. You will use the same judgment in P07 when deciding whether to add a critic or subagent.

Next: [P05: Memory + Compaction](../p05-memory/)
