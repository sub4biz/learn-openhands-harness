# P09: Model Routing Benchmark

| | |
|---|---|
| **What You Do** | Run the same 10 coding tasks three ways, then compare pass rate, tokens, cost, and cost per solved task. |
| **Harness Mechanism** | Rules routing, `RouterLLM`, LLM metrics, `LLMProfileStore`, `SwitchLLMTool`, and Laminar traces |

**Phase: ESCALATE ON EVIDENCE.** Routing is harness engineering. The frontier model is the consultant, not the default employee.

The lesson is not "always use the best model." It is "use the cheapest model you trust for this job, and escalate on evidence."

This is the advanced follow-up to [P02: Model Routing](../p02-model-routing/). P02 teaches the first routing idea with one prompt and one pre-conversation rule. P09 turns routing into an empirical harness experiment with 10 tasks, three runs, cost-per-solved-task, gated escalation, Agent Canvas switching, and Laminar traces.

## Directory Guide

| Path | What's inside |
|---|---|
| `toy_repo/` | The small Python package used for all 10 tasks. It has a CLI, date parsing, pagination, async code, auth middleware, API code, and tests. |
| `tasks.json` | The task manifest: `{id, prompt, difficulty, tags, paths, success_check}`. |
| `check_task.py` | Programmatic success checks. Task 9 uses a heuristic security-review artifact check. |
| `starter/` | Scaffolds for the first two runs plus a separate SwitchLLM cascade scaffold. |
| `solution/` | The completed lesson. Start with `run_frontier.py`, `run_static_rules.py`, and `run_switch_cascade.py`. |

For the learner path, open only these files first:

| Step | Starter | Solution |
|---|---|---|
| Baseline and rules router | `starter/run_routing.py` | `solution/run_frontier.py`, `solution/run_static_rules.py` |
| Cascade with profile switching | `starter/run_switch_cascade.py` | `solution/run_switch_cascade.py` |

Support files:

- `solution/routing_core.py`: shared local runner internals.
- `solution/run_all.py`: setup checks and local dry runs.

## The Problem Shape

You will run the same task set three ways:

1. `frontier`: use one model for every task. This is the baseline.
2. `static`: build a rules router with `RouterLLM`. Route once at task start, then never escalate.
3. `cascade`: start from the rules route, then use `SwitchLLMTool` and OpenHands profiles to move up when the trace shows the current model is stuck.

Only the second and third runs are routing strategies. The first run is there so the comparison has a simple control.

The solution keeps the learner-facing paths as three distinct entry points:

```bash
cd projects/p09-model-routing-benchmark/solution

uv run --with openhands-sdk --with openhands-tools --with pytest python run_frontier.py
uv run --with openhands-sdk --with openhands-tools --with pytest python run_static_rules.py
uv run --with openhands-sdk --with openhands-tools --with pytest python run_switch_cascade.py --setup-profiles --save-profile-secrets --task p09-task-08
```

For the full Agent Canvas cascade run, use:

```bash
uv run --with openhands-sdk --with openhands-tools --with pytest python run_switch_cascade.py --setup-profiles --save-profile-secrets --all-tasks
```

Use `run_all.py` only for local setup checks such as dry runs, model printing, and preflight model calls. The learner-facing cascade is `run_switch_cascade.py` because the model change appears in the Agent Canvas timeline as a profile switch.

## Before You Run

Pause and predict:

- Which tasks should be cheap by default?
- Which tasks should be protected by a risk floor?
- Which task do you expect to fail on the cheap tier first?
- What evidence should trigger escalation: repeated test failure, repeated error, repeated edits, turn budget, or unchanged diff?
- What cost reduction still matters if routing fails one task?

The headline metric is **cost per solved task**, not raw cost. Raw cost overclaims when a cheaper strategy fails.

The static baseline is intentionally budgeted. If rules choose CHEAP, that task gets the cheap-tier trust budget and no recovery path. A task labeled hard that routes to CHEAP because the prompt is short gets a one-call trust budget. The cascade uses the same budget as evidence, but can continue by moving one tier up.

## Task Set

The tasks are intentionally skewed toward routine work because that is where routing saves money:

1. Rename a variable across one file.
2. Write docstrings for 3 functions.
3. Fix a failing test with a wrong assertion value.
4. Add a `--verbose` CLI flag.
5. Write unit tests for date parsing.
6. Fix an off-by-one pagination bug.
7. Refactor a long report function into modules.
8. Debug an async race condition without serializing the simulated async work.
9. Review auth middleware for security issues.
10. Implement an API-specific caching layer with constructor injection for the backend client, clock, and per-resource TTLs, plus invalidation dependencies, request coalescing, failed-fill cleanup, fail-open stale reads that do not refresh the stale TTL, and backend-fill metrics.

Each live run starts from a fresh copy of `toy_repo/` under `.openhands-runs/p09/...`.

This is a transparent teaching benchmark by default. The prompt includes the task-specific validator command, so the agent can inspect `check_task.py` if it chooses. That makes the Agent Canvas recording easier to follow, but it is not the same as a hidden-test benchmark.

For stronger model-quality separation, run the solution with `--opaque-checks` or `P09_OPAQUE_CHECKS=1`. The harness still calls `check_task(repo, task.id)` after the conversation, but the validator path is not included in the agent prompt.

## Model Tiers

The scripts use three OpenHands `LLM` objects:

| Tier | Default model env var | Default model |
|---|---|---|
| CHEAP | `P09_MODEL_CHEAP` | `anthropic/claude-haiku-4-5-20251001` |
| MID | `P09_MODEL_MID` | `anthropic/claude-sonnet-4-6` |
| FRONTIER | `P09_MODEL_FRONTIER` | `anthropic/claude-opus-4-8` |

Set `LLM_API_KEY` for the provider, either in your shell or in the repo-level `.env`. Set `LLM_BASE_URL` if you are using a gateway or proxy. The scripts load the nearest `.env` before importing OpenHands so tracing and model credentials are available during SDK setup. They use OpenHands SDK metrics for token counts and accumulated cost. Do not paste invented per-task costs into your writeup.

Check what the benchmark will use before spending money:

```bash
uv run --with openhands-sdk --with openhands-tools --with pytest python run_all.py --print-models
```

Call each configured model once:

```bash
uv run --with openhands-sdk --with openhands-tools --with pytest python run_all.py --preflight-models
```

The single-model and `RouterLLM` rules runs select models directly from `P09_MODEL_*`. The cascade run uses Agent Server profiles named `p09-cheap`, `p09-mid`, and `p09-frontier` because `SwitchLLMTool` switches by profile name.

## Router Design

Keep the lesson path simple. Learners build two routing strategies after they run the single-model baseline.

### Run 1: Single Model Baseline

Run every task with the frontier tier. This is not the recommendation. It is the control group.

What to measure:

- Total cost.
- Tasks passed.
- Cost per solved task.
- Which tasks looked routine enough that frontier felt wasteful.

### Run 2: Rules Router With RouterLLM

Start the coding exercise here. `RouterLLM` is the right first mechanism because the harness chooses the model while the agent code stays unchanged.

Implement a static router:

- Create three `LLM` instances: CHEAP, MID, and FRONTIER.
- Pass them to `RouterLLM` as `llms_for_routing`.
- Implement `select_llm(messages) -> str`.
- Pick the route once from task metadata.
- Keep returning the same tier for the rest of that task.

Rules to start with:

- If the task touches auth or security tags/paths, route to FRONTIER.
- Risk floors override cost optimization.
- Never route high-risk work down.
- Prompt under 200 approximate tokens and no code block: CHEAP.
- Difficulty hard: FRONTIER.
- Else: MID.



### Run 3: Cascade With SwitchLLMTool

Use OpenHands profiles for cascade because the model needs to change along the path, after the conversation has already started.

The cascade run has three pieces:

- Profiles named `p09-cheap`, `p09-mid`, and `p09-frontier`.
- `SwitchLLMTool` enabled in the agent's tool list.
- Harness instructions that tell the agent exactly when to switch and what evidence to include.

The starting profile still comes from the rules route. The escalation decision should not be vague. Use deterministic evidence from the conversation:

- Do not run an LLM judge every turn.
- Same test failing twice.
- Same file changed 3 or more times. File views do not count.
- Identical error string repeating.
- Turn count exceeding the tier budget. Hard tasks on CHEAP use a one-call trust budget.
- Diff unchanged for 2 turns.

For the Canvas version, the evidence is written into the `switch_llm` call reason. That is the moment to show in the recording.

Example tool-call reason:

```json
{"profile_name": "p09-mid", "reason": "same pagination assertion failed twice after two edits"}
```

Optional extension: add a cheap judge only after a deterministic trigger fires. Feed it a condensed state summary: task, current tier, last 3 actions, last 2 errors, test status, and trigger list. Do not send raw tool output.

## Choosing The OpenHands Mechanism

Before writing code, decide where the routing decision should live.

Ask two questions:

- Is the model chosen once before the task really starts?
- Or can the model change after the agent has seen tests, errors, edits, and tool output?

That choice determines the OpenHands mechanism.

| Design need | Use | Why |
|---|---|---|
| Pick a model once from task metadata | `RouterLLM` | The harness owns the rule, and the agent code stays unchanged. |
| Change models during an Agent Canvas run | `SwitchLLMTool` plus profiles | The conversation is already running, so the switch needs to happen through a profile change that Canvas can show. |

### Static Rules: Use RouterLLM

For the rules router, the decision happens at the start of the task. That is a good fit for `RouterLLM`.

The design target:

- The harness creates CHEAP, MID, and FRONTIER `LLM` objects.
- The harness passes them to `RouterLLM`.
- `select_llm(messages)` returns the tier name.
- The route is based on task metadata and risk floors.
- The same tier is returned for the rest of the task.

The learner should be able to read the routing policy as ordinary code:

```python
if touches_auth_or_security(task):
    return "frontier"
if prompt_tokens(task.prompt) < 200 and "```" not in task.prompt:
    return "cheap"
if task.difficulty == "hard":
    return "frontier"
return "mid"
```

Current API shape, verified against OpenHands SDK v1.26.0:

- `RouterLLM.select_llm(self, messages: list[Message]) -> str`
- `select_llm` receives conversation messages, not the raw SDK event stream.
- For static rules, the router can ignore most message content and use task metadata captured on the router instance.

Important remote caveat: in v1.26.0, `RouterLLM` still serializes through `RemoteConversation` as a plain `LLM` with `model` equal to the router name. That is fine for local SDK runs, but it is not the best mechanism for a visible Agent Canvas switch.

### Cascade: Use Profiles Plus SwitchLLMTool

For the cascade, the decision happens after the run has started. The agent might need to see the same test fail twice or the same file get edited several times before moving up. That is why cascade uses profiles and `SwitchLLMTool`.

The design target:

- Create profiles named `p09-cheap`, `p09-mid`, and `p09-frontier`.
- Start on the tier selected by the rules route.
- Enable `SwitchLLMTool`.
- Put the escalation policy in the harness instructions.
- Require an evidence-based switch reason.

This is the difference learners should see: `RouterLLM` hides routing from the agent, while `SwitchLLMTool` makes the switch an explicit event in the conversation.

Run it against Agent Canvas:

```bash
cd projects/p09-model-routing-benchmark/solution

LLM_API_KEY=... \
uv run --with openhands-sdk --with openhands-tools --with pytest \
  python run_switch_cascade.py --setup-profiles --save-profile-secrets --task p09-task-08
```

If you do not want the script to save secrets in `~/.openhands/profiles`, create encrypted profiles in the Canvas settings UI named `p09-cheap`, `p09-mid`, and `p09-frontier`, then omit `--setup-profiles`.

Canvas renders the switch as a "Switch LLM profile" event. That makes the cascade useful for screen recording. The tradeoff is control: the harness defines the policy, but the model has to call the switching tool when the evidence appears.

## Laminar Traces

OpenHands SDK tracing is automatic when the environment is configured. To send traces to Laminar:

```bash
export LMNR_PROJECT_API_KEY="..."
export P09_TRACE_USER_ID="raj-p09"
```

Then run any solution script normally. Each conversation is tagged with `lesson=p09`, `strategy`, and `task`, and OpenHands emits spans for agent steps, tool calls, LLM calls, and conversation lifecycle events.

The P09 scripts load the nearest repo-level `.env`, so the Laminar key you put there is enough. Existing shell values take precedence.

By default, `P09_TRACE_MODE=auto` converts a repo-level `LMNR_PROJECT_API_KEY` into Laminar's OTLP HTTP endpoint before OpenHands imports its tracing hooks.

The scripts also set:

```bash
GRPC_ENABLE_FORK_SUPPORT=true
GRPC_POLL_STRATEGY=poll
GRPC_VERBOSITY=ERROR
```

That last setting matters for local SDK runs. The OpenHands terminal tool uses tmux; without `GRPC_VERBOSITY=ERROR`, gRPC can emit an info-level fork diagnostic to stderr when tmux panes are created, and libtmux treats any stderr from `tmux new-window` as a command failure.

Trace modes:

| Mode | Behavior |
|---|---|
| `auto` | If `LMNR_PROJECT_API_KEY` is set, send traces to Laminar through OTLP HTTP. |
| `laminar-http` | Force Laminar OTLP HTTP. |
| `laminar-grpc` | Keep OpenHands' native Laminar SDK path. Use this if your local terminal tools do not hit gRPC fork errors. |
| `off` | Unset tracing env vars for the run. Use this if you want benchmark metrics without external traces. |

For a self-hosted Laminar HTTP endpoint, set `P09_LAMINAR_HTTP_ENDPOINT`.

## Smoke Checks

Dry-run routing without paid LLM calls:

```bash
cd projects/p09-model-routing-benchmark/solution
uv run --with openhands-sdk --with openhands-tools --with pytest python run_all.py --dry-run
```

Run one local measured task:

```bash
LLM_API_KEY=... \
uv run --with openhands-sdk --with openhands-tools --with pytest \
  python run_static_rules.py --task p09-task-10
```

Run one Canvas-visible cascade task:

```bash
LLM_API_KEY=... \
uv run --with openhands-sdk --with openhands-tools --with pytest \
  python run_switch_cascade.py --setup-profiles --save-profile-secrets --task p09-task-10
```

Task 10 is the expected escalation smoke test. Static rules cap the hard task's cheap run at the smaller trust budget and have no recovery path. The cascade starts from the same route, then should call `switch_llm` after evidence such as the one-call cheap trust budget, failed stale-refresh checks, failed-fill checks, or later budget triggers. You need at least one real profile-switch event in the Canvas trace before claiming the lesson works.

Instructor calibration from June 5, 2026: task 10 produced the intended separation on this repo. Static rules started cheap and failed after the cheap trust budget. Cascade started cheap, moved to mid, and passed. Re-measure before recording because model behavior and costs change.

## What To Record

Per strategy:

| Task | Model(s) used | Attempts | Escalations | Tokens | Cost | Pass/fail |
|---|---|---:|---:|---:|---:|---|
| p09-task-01 | | | | | | |

Summary:

| Strategy | Tasks passed | Total cost | Cost per solved task |
|---|---:|---:|---:|
| frontier | | | |
| static | | | |
| cascade | | | |

Label your numbers as "measured on this repo, your mileage varies."

## References

- [RouteLLM, LMSYS/Berkeley](https://www.lmsys.org/blog/2024-07-01-routellm/) and [paper](https://arxiv.org/abs/2406.18665): reported cost reductions over GPT-4-only of more than 85 percent on MT Bench, 45 percent on MMLU, and 35 percent on GSM8K while retaining 95 percent of GPT-4 performance. The matrix-factorization router reached 95 percent quality with 26 percent GPT-4 calls, or 14 percent with augmented data.
- [Anyscale router tutorial](https://www.anyscale.com/blog/building-an-llm-router-for-high-quality-and-cost-effective-responses): classifier and matrix-factorization router tutorial with MT Bench routing comparisons.
- [GPT-5 system card](https://openai.com/index/gpt-5-system-card/): classifier-style real-time router between fast and thinking models, trained on signals such as model switches, preference rates, and measured correctness.
- [Harvey Legal Agent Benchmark initial results](https://www.harvey.ai/blog/legal-agent-benchmark-initial-results): published benchmark results show the cost and latency pressure around frontier-only agents. Phrase these as published results, not production claims.
- [OpenHands SDK API reference: LLM](https://docs.openhands.dev/sdk/api-reference/openhands.sdk.llm): `RouterLLM`, `LLMProfileStore`, metrics, and token/cost tracking.
- [OpenHands observability guide](https://docs.openhands.dev/sdk/guides/observability): Laminar and OTLP tracing configuration.
- [OpenHands SDK paper](https://arxiv.org/abs/2511.03690): SDK architecture and model routing design.

## What You Keep

A routing policy you can defend with traces and metrics:

- Risk floors for tasks you should never route down.
- Cheap default for routine work.
- Evidence-based escalation before paying frontier cost.
- Cost per solved task as the comparison metric.

Save the policy and the result table. They are the advanced version of the simple P02 routing artifact.

Previous routing lesson: [P02: Model Routing](../p02-model-routing/)
