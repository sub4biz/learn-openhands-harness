# P01 — Canvas + Agent Trace

| | |
|---|---|
| **What You Do** | Run one narrow task through the canvas, then read the agent trace. Count tool calls, inspect observations, and save the trace as your baseline. |
| **Harness Mechanism** | Agent Server typed events + persisted conversation events + Canvas trace viewer |

**Phase: SEE THE LOOP.** Before changing any knobs, learn to read the loop. The differentiator here is not that the agent can call tools. Claude Code, Cursor, and OpenHands can all do that. The differentiator is that the harness trace is visible, queryable, forkable, and reusable as evaluation data.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_baseline.py` — runs the prompt and prints raw event count + cost. The minimum viable SDK run. |
| `solution/` | `run_baseline.py` — same script, extended to print a structured trace summary. Plus `trace_checklist.md` — the trace-reading checklist to keep. |

## Setup

- Same repo and same prompt for the rest of the projects.
- Use the default canvas setup from the [quickstart](../../01-quickstart.md).
- Set `WORKSPACE_DIR=/path/to/that/repo` before running the SDK scripts.
- Good default prompt: `"Find every place VITE_BACKEND_HOST is read or set, and write a short note explaining how the dev script picks the backend."`

## Procedure

1. Start a fresh conversation in the canvas and run the prompt to completion.
2. Open the agent trace. Identify: user message, assistant planning, each tool call, each observation, final answer, and any compaction placeholder.
3. Save the agent trace from `GET /api/conversations/{id}/events/search` or the canvas UI if export is available in your build. OpenHands stores the trace as typed events; "agent trace" is the teaching term.
4. Record the working directory, repo SHA, model, active tool list, number of tool calls, wall-clock time, cost, and whether the final answer cited real files.
5. Run `starter/run_baseline.py` to repeat the same task via the SDK. Compare your SDK trace to the canvas trace — they should match.

## What to write down

| Trace field | Value |
|---|---|
| Repo + SHA | |
| Prompt | |
| Model | |
| Active tools | |
| Tool calls by type | |
| Files read | |
| Files edited | |
| Compaction fired? | |
| Final answer correct? | |

## What to look for

- The agent trace is the unit of diagnosis. If the final answer is wrong, find the first bad observation or skipped retrieval step.
- A healthy code-reading run has a small number of targeted searches and file reads before answering.
- A harness you cannot inspect cannot be tuned. This baseline trace is what makes the later ablations meaningful.

## What you keep

One baseline agent trace plus a trace-reading checklist (see `solution/trace_checklist.md`). Every later project compares against this trace, not against vibes.

→ Next: [P02 — Model Routing](../p02-model-routing/)
