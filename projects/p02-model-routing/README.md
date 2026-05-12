# P02 — Model Routing

| | |
|---|---|
| **What You Do** | Run the same prompt three ways: flagship LLM, small LLM, and a router-backed config. Compare turns, tokens, cost, and where the cost lands. |
| **Harness Mechanism** | [`LLMRegistry`](https://docs.openhands.dev/sdk/guides/llm-registry) + [`RouterLLM`](https://docs.openhands.dev/sdk/guides/llm-routing) (e.g. `MultimodalRouter`) |

**Phase: RIGHT-SIZE THE THINKING.** Most operators leave the model lever untouched. This project changes that.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_routing.py` — runs a single flagship model with TODOs for adding a small model and a router. |
| `solution/` | `run_routing.py` — all three configs (flagship, small, routed) with per-config metrics printed side by side. |

## Setup

- Same agent server, same canvas, same workspace.
- Same baseline trace fields from P01.
- Same prompt, same active tool list.
- Three configs:
  - **A — flagship:** e.g. `anthropic/claude-sonnet-4-5-20250929`.
  - **B — small:** e.g. `openai/gpt-5-mini-2025-08-07` or `anthropic/claude-haiku-4-5-20251001`.
  - **C — routed:** a `RouterLLM`. The solution uses the shipped `MultimodalRouter`: image-bearing or over-context calls go to the flagship, ordinary text calls go to the small model. For a text-only prompt, that means you should expect most or all routed calls to land on the small model; if you want mixed text routing, use an importable custom router policy.

## Procedure

1. Start a conversation with config A. Run to completion. Record: turn count, in/out tokens *per `usage_id`*, accumulated cost, correctness.
2. Fork from start (or re-create) and run config B. Same metrics.
3. Run config C. Same metrics — but now `get_combined_metrics()` will break the cost down by leg of the router. Note which calls actually went to which model, and whether that matches the router policy.

## What to write down

| Config | Turns | In tokens | Out tokens | Cost | Correct? | Where the cost landed |
|---|---|---|---|---|---|---|
| A flagship | | | | | | 100% flagship |
| B small | | | | | | 100% small |
| C routed | | | | | | _e.g. 20% flagship / 80% small_ |

## What to look for

- Turn-count differences across A and B are usually about *retrieval discipline* (does the model grep enough before guessing?), not raw intelligence. If the cheaper model uses fewer turns and gets the same answer, it's not because it's smarter — it's because the task didn't need the extra capability.
- Config C is the interesting one. If it lands within 10% of A's correctness at 30% of A's cost, you have evidence that *most of your task doesn't need the flagship*. If C drops sharply on correctness, your routing policy is sending the wrong things to the small model — fix the policy, not the models.

> Connection to the talk: slide 11 (same model, 2× gap from harness) and slide 22's framing of the model as *one of five levers, not the dominant one*.

### Supporting note — tool surface and schema

Tool selection matters, but by itself it is not the differentiator. Claude Code, Cursor, and OpenHands all expose tool controls and MCP integrations. The interesting harness question is whether a tool's schema and runtime boundary make bad actions harder.

Keep this as a quick sanity check rather than a full project: compare a `terminal`-only run with the default `terminal + file_editor + task_tracker` run. If the shell-only agent overwrites files or loses context, write down the failure mode. The lesson is schema-enforced behavior, not "more tools."

## What you keep

A `RouterLLM` or `LLMRegistry` configuration that lands within 10% of flagship correctness at 30–50% of flagship cost. Save the Python snippet (5–20 lines) verbatim. You'll paste it into `harness.py` in P06.

→ Next: [P03 — Retrieval](../p03-retrieval/)
