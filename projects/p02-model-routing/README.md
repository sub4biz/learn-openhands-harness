# P02: Model Routing

## What Problem Are You Solving?

Most operators leave the model lever untouched and pay flagship prices for tasks a small model would finish just as well. Model choice is a harness decision: classify the task first, then give the agent the cheapest model that can do it.

This is the first routing lesson, so it stays small. You run the same prompt three ways and compare turns, tokens, cost, and where the cost lands:

1. **Flagship** model for everything. The expensive control.
2. **Small** model for everything. The cheap control.
3. **Routed.** A small function picks one concrete `LLM` before the conversation starts: ordinary text and code-search prompts go to the small model, while image, security, architecture, or multi-file-edit prompts go to the flagship.

The richer version (gated escalation, `RouterLLM`, `SwitchLLMTool`, model-switch events, traces) is [P09: Model Routing Benchmark](../p09-model-routing-benchmark/). P02 is the preflight decision; P09 turns it into a measured benchmark.

## Start With These Files

Open this README and `starter/` only. Ask your coding agent to complete the TODOs without reading `solution/`, run the command below, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| Run the configs | `starter/run_routing.py` (flagship + TODOs for small and routed) | `solution/run_routing.py` (all three, metrics side by side) |

The artifact you keep here, a routing policy that holds correctness while cutting cost, gets pasted into `harness.py` in P07.

## The Three Configurations

Hold everything else constant from P01: same agent server, same workspace, same prompt, same active tool list, same baseline trace fields. Only the model changes.

| Config | Model | Expectation |
|---|---|---|
| A: flagship | e.g. `anthropic/claude-sonnet-4-5-20250929` | 100% flagship cost, the correctness ceiling |
| B: small | e.g. `anthropic/claude-haiku-4-5-20251001` | 100% small cost, the cheap floor |
| C: routed | a function selects one before the run | small for routine prompts, flagship for hard ones |

This is the remote-safe pattern: classify the task in the harness, then construct the agent with the selected concrete `LLM`.

Before you run, predict. Which model should the router pick for the default backend env-var prompt (it is text-only, so the shipped policy should pick small)? What prompt words should force the flagship branch? What cost reduction would make routing worth keeping? What failure would prove the router is too aggressive?

## Run It And Collect Metrics

```bash
cd projects/p02-model-routing/solution
uv run --with openhands-sdk --with openhands-tools python run_routing.py
```

Run config A to completion and record turns, in/out tokens, cost, and correctness. Recreate (or fork from start) and run B, then C, recording the same. Note which model the policy chose for C and whether that matches your intent.

The default prompt is text-only, so C should select the small model. To prove the flagship branch exists, rerun with a flagship marker in the prompt:

```bash
P02_PROMPT="Review the security model and propose architecture changes." \
uv run --with openhands-sdk --with openhands-tools python run_routing.py
```

## Record The Results

| Config | Turns | In tokens | Out tokens | Cost | Correct? | Where the cost landed |
|---|---:|---:|---:|---:|---|---|
| A flagship | | | | | | 100% flagship |
| B small | | | | | | 100% small |
| C routed | | | | | | selected small or flagship |

## How To Read The Results

- Turn-count differences between A and B are usually about retrieval discipline, not raw intelligence. If the cheaper model uses fewer turns and gets the same answer, the task did not need the extra capability.
- Config C is the one that matters. If it lands within 10% of A's correctness at 30 to 50% of A's cost, most of your work does not need the flagship.
- If C drops sharply on correctness, the policy is sending the wrong task type to the small model. Fix the policy, not the models.

Tool surface is a related lever, but not the differentiator on its own. Claude Code, Cursor, and OpenHands all expose tool controls. The real question is whether a tool's schema and runtime boundary make bad actions harder. As a quick check, compare a `terminal`-only run with the default `terminal + file_editor + task_tracker` run; if the shell-only agent overwrites files or loses context, write down the failure mode. The lesson is schema-enforced behavior, not "more tools."

<details>
<summary>References</summary>

- [LLMRegistry](https://docs.openhands.dev/sdk/guides/llm-registry): managing multiple models in a larger harness.
- [P09: Model Routing Benchmark](../p09-model-routing-benchmark/): the measured, escalating version of this lever.
- [Harness engineering talk and slides](https://github.com/rajshah4/harness-engineering#presentation-materials): the same model performs very differently under different harnesses.

</details>

## What Students Should Leave With

A routing policy (or `LLMRegistry` configuration) that lands within 10% of flagship correctness at 30 to 50% of flagship cost. Save the Python snippet verbatim; you will paste it into `harness.py` in P07.

Next: [P03: Retrieval](../p03-retrieval/)
