# P02: Model Routing

| | |
|---|---|
| **What You Do** | Run the same prompt three ways: flagship LLM, small LLM, and a routed config. Compare turns, tokens, cost, and where the cost lands. |
| **Harness Mechanism** | Remote-safe model selection before agent construction; [`LLMRegistry`](https://docs.openhands.dev/sdk/guides/llm-registry) for larger harnesses |

**Phase: RIGHT-SIZE THE THINKING.** Most operators leave the model lever untouched. This project changes that.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_routing.py`. runs a single flagship model with TODOs for adding a small model and a routing policy. |
| `solution/` | `run_routing.py`. all three configs (flagship, small, routed) with per-config metrics printed side by side. |

## Setup

- Same agent server, same canvas, same workspace.
- Same baseline trace fields from P01.
- Same prompt, same active tool list.
- Three configs:
  - **A: flagship:** e.g. `anthropic/claude-sonnet-4-5-20250929`.
  - **B: small:** e.g. `openai/gpt-5-mini-2025-08-07` or `anthropic/claude-haiku-4-5-20251001`.
  - **C: routed:** a small routing function chooses one concrete `LLM` before the remote conversation starts. Ordinary text/code-search prompts go to the small model; image, security, architecture, or multi-file edit prompts go to the flagship.

> **SDK 1.22.x note:** `RouterLLM` objects such as `MultimodalRouter` do not
> currently survive the `RemoteConversation` boundary used by the Agent Canvas
> agent server. The server receives the literal model name `router` and LiteLLM
> rejects it. This project therefore teaches a remote-safe pattern: classify the
> task in the harness, then create the agent with the selected concrete `LLM`.
> If router-aware remote serialization lands in a later SDK, the kept policy can
> move back into a `RouterLLM`.

## Procedure

1. Start a conversation with config A. Run to completion. Record: turn count, in/out tokens *per `usage_id`*, accumulated cost, correctness.
2. Fork from start (or re-create) and run config B. Same metrics.
3. Run config C. Same metrics. Note which model the policy selected and whether that matches your intent.

## What to write down

| Config | Turns | In tokens | Out tokens | Cost | Correct? | Where the cost landed |
|---|---|---|---|---|---|---|
| A flagship | | | | | | 100% flagship |
| B small | | | | | | 100% small |
| C routed | | | | | | _e.g. selected small for this text-only task_ |

## What to look for

- Turn-count differences across A and B are usually about *retrieval discipline* (does the model grep enough before guessing?), not raw intelligence. If the cheaper model uses fewer turns and gets the same answer, it's not because it's smarter, because the task didn't need the extra capability.
- Config C is the interesting one. If it lands within 10% of A's correctness at 30% of A's cost, you have evidence that *most of your task doesn't need the flagship*. If C drops sharply on correctness, your routing policy is sending the wrong task type to the small model. Fix the policy, not the models.

> Connection to the talk: slide 11 (same model, 2× gap from harness) and slide 22's framing of the model as *one of five levers, not the dominant one*.

### Supporting note: tool surface and schema

Tool selection matters, but by itself it is not the differentiator. Claude Code, Cursor, and OpenHands all expose tool controls and MCP integrations. The interesting harness question is whether a tool's schema and runtime boundary make bad actions harder.

Keep this as a quick sanity check rather than a full project: compare a `terminal`-only run with the default `terminal + file_editor + task_tracker` run. If the shell-only agent overwrites files or loses context, write down the failure mode. The lesson is schema-enforced behavior, not "more tools."

## What you keep

A routing policy or `LLMRegistry` configuration that lands within 10% of flagship correctness at 30–50% of flagship cost. Save the Python snippet (5–20 lines) verbatim. You'll paste it into `harness.py` in P07.

→ Next: [P03: Retrieval](../p03-retrieval/)
