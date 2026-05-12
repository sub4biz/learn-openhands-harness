# Projects — Learning Path

Six small projects, in order, each changing one harness lever and producing a config artifact that carries forward. By P06 you'll have a runnable `harness.py` and an agent-trace evaluation record that wires together everything you kept — your trace-reading checklist, model routing, retrieval decision, memory policy, security profile, sandbox, and critic.

If you're using this as a first learning path, treat P01-P04 as the core concepts. P05-P06 are the advanced path where safety, verification, and composition start looking like production harness design.

The pattern is behavior first: decide what agent behavior you want, change the smallest harness surface that could affect it, then observe whether the trace changed.

> **Inspired by [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering)**, which organizes harness learning as a sequence of cumulative projects on the same Electron app rather than disconnected one-off ablations. That's a better shape for learning than the standard "here are some experiments" format, and it adapts naturally to OpenHands. The phase names, the two-column "What You Do / Harness Mechanism" preamble, and the "each project's solution becomes the next project's starter" property are all borrowed from there. Credit where it's due.

> **Common task across all projects.** Pick one repo and one prompt, and freeze them. A good default: clone [`OpenHands/agent-canvas`](https://github.com/OpenHands/agent-canvas) and use the prompt `"Find every place VITE_BACKEND_HOST is read or set, and write a short note explaining how the dev script picks the backend."` — narrow, repeatable, doesn't write code, and forces real retrieval.

---

## Project evolution

```text
PROJECT EVOLUTION (OpenHands harness)
=====================================

  P01  Canvas + agent trace          → SEE THE LOOP
       |                               keep: a baseline trace
       |                                     + trace-reading checklist
       v
  P02  Model routing                 → RIGHT-SIZE THE THINKING
       |                               keep: a RouterLLM / LLMRegistry config
       v
  P03  Retrieval                     → STOP HALLUCINATED PATHS
       |                               keep: a one-line decision rule
       |                                     for when MCP earns its slot
       v
  P04  Memory + compaction           → REDUCE RE-DISCOVERY
       |                               keep: a hand-written AGENTS.md
       |                                     + condenser/memory notes
       v
  P05  Org safety profile            → BOUND BLAST RADIUS
       |                               keep: org security profile
       |                                     + DockerWorkspace runner
       v
  P06  Verification + capstone       → STOP "LOOKS FINE"
                                       keep: Critic + rubric + harness.py

  Each project produces a concrete artifact.
  P06 is where they merge into one runnable harness.
```

---

## How each project is organized

Every project directory follows the same shape:

```
p01-agent-trace/
├── README.md       ← instructions, setup, procedure, what to record
├── starter/        ← starting point — run this first
└── solution/       ← reference implementation — check your work
```

Each project README has:
- A two-row preamble: **What You Do** / **Harness Mechanism**.
- Setup, procedure, and what to record.
- A **What you keep** callout at the end — the artifact that carries forward.

Use a fresh conversation per run. Save agent traces.

---

## Running the scripts

All scripts are designed to be run with `uv run`:

```bash
cd projects/p01-agent-trace/starter
uv run --with openhands-sdk --with openhands-tools python run_baseline.py
```

Required environment variables for every script:

```bash
export LLM_API_KEY="sk-..."
export LLM_MODEL="anthropic/claude-sonnet-4-5-20250929"
```

---

## Tabulating your results

Keep a `results.md` next to your fork:

```markdown
# Harness projects — <date>

Repo: agent-canvas @ <SHA>
Model: anthropic/claude-sonnet-4-5-20250929 (unless noted)
Prompt: "Find every place VITE_BACKEND_HOST is read or set..."

## P01: Canvas + agent trace
| Trace field | Value |
|---|---|
| Tool calls by type | |
| Files read | |
| Compaction fired? | |
| Final answer correct? | |

## P02: Model routing
| Config | Turns | Tokens (in/out) | Cost | Correct |
|---|---|---|---|---|
| Sonnet 4.5 | | | | |
| Small model | | | | |
| Routed | | | | |

## P03: Retrieval
| Config | Tool calls (grep) | Tool calls (MCP) | Correct | Notes |
|---|---|---|---|---|
| Lexical only | | — | | |
| Lexical + MCP | | | | |

## P04: Memory + compaction
| Config | Turns | Tokens | Correct | Notes |
|---|---|---|---|---|
| No AGENTS.md | | | | |
| Minimal AGENTS.md | | | | |

## P05: Org safety profile
| Action | Expected risk | Actual behavior | Accept? |
|---|---|---|---|
| Read files | LOW | | |
| Edit workspace file | LOW/MEDIUM | | |
| Network/package install | HIGH | | |
| Delete file | HIGH | | |

## P06: Verification + capstone
| Config | Pass rate (n=5) | Median iterations | Median cost | Wall-clock |
|---|---|---|---|---|
| No critic | | | | |
| Critic | | | | |
```

Three runs is barely a signal; ten is convincing; thirty is real. Pick a budget and stick to it.

---

## Where to go from here

`harness.py` exists. The next question is whether you are turning it into a shared platform or just adding integrations.

Prioritize these if the harness will be used by a team:

- **Persistence as the audit substrate.** Persist events, agent configuration, execution state, tool outputs, metrics, workspace context, activated skills, and secrets so every run can be replayed and evaluated. ([Persistence guide](https://docs.openhands.dev/sdk/guides/convo-persistence).)
- **Observability before shared service.** Emit OpenTelemetry traces for agent steps, tool calls, LLM calls, browser sessions, and conversation lifecycle events. This is how operations teams debug the harness instead of reading screenshots. ([Observability guide](https://docs.openhands.dev/sdk/guides/observability).)
- **AgentSettings for admin-controlled profiles.** If Canvas or an internal UI will select "local dev", "company repo", or "regulated" profiles, serialize those knobs as validated settings rather than loose Python. ([Agent Settings guide](https://docs.openhands.dev/sdk/guides/agent-settings).)
- **Secret handling as part of P05.** `conversation.update_secrets(...)` injects secrets only when needed and masks values in output. Do not treat secrets as generic environment variables once real systems are involved. ([Secret Registry guide](https://docs.openhands.dev/sdk/guides/secrets).)
- **LLM fallback for production reliability.** `FallbackStrategy` retries alternate model profiles for rate limits and timeouts while keeping cost metrics visible. ([LLM Fallback guide](https://docs.openhands.dev/sdk/guides/llm-fallback).)

Keep these as supporting tools, not the tutorial spine:

- **Hooks** are useful for hard-deny rules and protocol checks, but Claude Code has hooks too. Use them when they enforce your P05 safety profile. ([Hooks guide](https://docs.openhands.dev/sdk/guides/hooks).)
- **Custom tools** matter when the schema changes behavior. "The agent can call another API" is not interesting by itself. ([Custom tools guide](https://docs.openhands.dev/sdk/guides/custom-tools).)
- **MCP** belongs in the retrieval ablation. It is table stakes unless the experiment proves it improves a vocabulary-mismatch task.
- **File-based agents and parallel tool execution** should wait until the single-agent trace is boring. They add coordination cost and shared-state risk. ([File-Based Agents guide](https://docs.openhands.dev/sdk/guides/agent-file-based), [Parallel Tool Execution guide](https://docs.openhands.dev/sdk/guides/parallel-tool-execution).)

That is the line this tutorial should hold: integrations are supporting cast; open harness ownership is the point.
