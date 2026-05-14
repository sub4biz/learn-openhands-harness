# Learn Harness Engineering on OpenHands

Every coding agent ships two things: a model that reasons and a harness that does everything else. The harness decides what the model sees, which tools it can call, what it remembers across turns, when it stops, and whether it runs in a sandbox or on your bare machine. When an agent breaks, it's almost never the model. It's a harness decision you didn't know you were making.

This tutorial gives you a working harness you can open, run, and change. You'll use two open-source projects, [Agent Server](https://docs.openhands.dev/sdk/arch/agent-server) (the HTTP API that owns the workspace, conversation state, and tool dispatch) and [Agent Canvas](https://github.com/OpenHands/agent-canvas) (the operator UI), as a microscope. You'll give the agent real tasks, read the trace of what happened, and then change one lever at a time to see the behavior shift.

By the end you'll have a `harness.py` you built yourself, with model routing, retrieval config, memory policy, a security profile, and a critic. More importantly, you'll be able to look at any agent product and answer: *what would I change about its harness if I owned the source?*

> **Background.** If you want the conceptual frame first, read the [harness-engineering README](https://github.com/rajshah4/harness-engineering) and watch the [talk](https://www.youtube.com/watch?v=KijChx7q2nY). This tutorial assumes you already buy the thesis: the model reasons, the harness does everything else.

---

## Why an open harness

There are good harnesses you can't see (Claude Code, Codex CLI, Cursor) and good ones you can (SWE-agent, OpenHands, deepagents). For learning, only the open ones work. You need to read the code to understand what a harness *is*.

OpenHands is a useful study target for three reasons:

1. **Clean client/server split.** The agent server is a stateless-ish HTTP API; the canvas is a thin client. The harness boundary is literally an OpenAPI spec. You can replace either side without rewriting the other.
2. **Three deployment shapes from one codebase.** Local process, Docker sandbox, hosted API, all by swapping a `Workspace` class. That makes the cost of *where work runs* visible.
3. **The trace is a first-class object.** The chronological record of messages, tool calls, results, compaction, and confirmations is right there in the canvas. You don't have to grep logs to see what the harness is doing.

The Anthropic [post-mortem on Claude Code's reasoning-effort regression](https://www.anthropic.com/engineering/claude-code-default-reasoning-effort-update) is a good reminder of what closed harnesses cost you. When the model didn't change but quality did, users had no way to diagnose it. The whole point of running an open harness is that you *can*.

---

## What you'll do

Three phases, in order. Each builds on the previous one.

1. **[Quickstart](./01-quickstart.md).** Install, get a green health check, and have a working canvas in front of you.
2. **[Harness tour](./02-harness-tour.md).** Give the agent a real task, read the trace, and see the five parts of a harness (model, tools, memory, safety, architecture) in the context of what actually happened.
3. **[Projects](./projects/).** Seven projects, each with a `starter/` and `solution/`. Change one lever at a time, keep the artifact, move on.

Each project follows the [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) pattern: `starter/` is your starting point, `solution/` is the reference. Each solution becomes the next project's foundation; by P07 you have a complete `harness.py` and an evaluation trace you can defend.

The most important habit is separating constants from variables. A model
router, security profile, default tool list, memory policy, and sandbox belong
in `harness.py` only after repeated runs show they should be stable defaults.
Task prompt, repo path, budget, and one-off exceptions stay outside the harness.
If you find yourself editing `harness.py` for every task, you still have a
prototype, not a harness you can trust.

| Project | What you change | What you keep |
|---|---|---|
| [P01: Agent Trace](./projects/p01-agent-trace/) | See the loop | Baseline trace + trace-reading checklist |
| [P02: Model Routing](./projects/p02-model-routing/) | Right-size the thinking | Routing policy / LLMRegistry config |
| [P03: Retrieval](./projects/p03-retrieval/) | Stop hallucinated paths | Grep-first MCP-on/off decision rule |
| [P04: Task Decomposition](./projects/p04-decomposition/) | Break down large work | Decomposition plan + aggregation rule |
| [P05: Memory](./projects/p05-memory/) | Reduce re-discovery | AGENTS.md + condenser/memory policy notes |
| [P06: Safety](./projects/p06-safety/) | Bound blast radius | Security profile + DockerWorkspace runner |
| [P07: Capstone](./projects/p07-capstone/) | Stop "looks fine" | Critic + rubric + harness.py |

---

## Prerequisites

- macOS or Linux (Windows works but the canvas dev script assumes a POSIX shell)
- **Node.js 22.12+** and `npm`
- **`uv`** ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **An LLM API key** (Anthropic, OpenAI, or anything [LiteLLM](https://docs.litellm.ai/docs/providers) supports)
- **Docker** is optional for the first walkthrough but recommended for real work

Details on how `uv`, the API key, and Docker fit together are in the [quickstart](./01-quickstart.md).

---

## Setup

Live agent runs need one secret: `LLM_API_KEY`. The checked-in scripts default to Sonnet 4.5, so `LLM_MODEL` is optional unless you want a different model.

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY to a provider key.
set -a
source .env
set +a
```

Optional knobs: `LLM_MODEL` for the main model, `LLM_MODEL_SMALL` for routing experiments, `WORKSPACE_DIR` for the repo the agent inspects. Never commit a real `.env`. If a key leaks, rotate it.

**Safety note.** This tutorial starts dockerless on purpose. That's the easiest way to see the agent server, HTTP API, filesystem, and trace without another layer in the way. But `npm run dev:dangerously-dockerless` runs tool calls directly on your host. Point it at a scratch repo, not one you care about. P06 moves you to Docker. Until then, treat dockerless mode as a learning microscope, not a safe operating mode.

---

## Further reading

None of this is required. The tutorial is self-contained.

**Harness engineering:**

- [Engineering the Harness (talk + slides)](https://github.com/rajshah4/harness-engineering#presentation-materials). The framing this repo is built around.
- [OpenAI: Harness engineering](https://openai.com/index/harness-engineering/). Codex team's take on their own harness design.
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). Compaction and long-running loop design.
- [walkinglabs / learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering). Project-based course. Heavier on convention than on plumbing; complements this tutorial well.

**OpenHands specifics:**

- [Agent Server architecture](https://docs.openhands.dev/sdk/arch/agent-server). Design intent.
- [Agent Server: Local](https://docs.openhands.dev/sdk/guides/agent-server/local-server) and [Docker Sandbox](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox) guides.
- [`OpenHands/agent-canvas`](https://github.com/OpenHands/agent-canvas). The UI. The `DEVELOPMENT.md` is unusually honest about which knobs you actually have.
- [`OpenHands/software-agent-sdk`](https://github.com/OpenHands/software-agent-sdk). The SDK the server is built on.

---

## Where to go from here

After P07 you have a working `harness.py` and the mental model to extend it. A few directions worth exploring:

- **More use cases.** The [OpenHands use cases overview](https://docs.openhands.dev/openhands/usage/use-cases/overview) shows what people are building with coding harnesses beyond the tutorial tasks: migrations, test generation, documentation, issue triage. Good source of fresh prompts to stress-test your harness against.
- **Multi-agent orchestration.** This tutorial builds a single-agent harness. The [openhands-multi-agent-demo](https://github.com/rajshah4/openhands-multi-agent-demo) shows the next step: composing multiple harnesses (Claude Code, Gemini CLI, OpenHands) into an implement, test, review pipeline. Three orchestration patterns, same workflow, different isolation and state-sharing tradeoffs.
- **Extend the harness.** The tutorial covers the core levers, but there is more surface area to work with: [custom tools](https://docs.openhands.dev/sdk/guides/tool), [MCP servers](https://docs.openhands.dev/sdk/guides/mcp), [skills](https://docs.openhands.dev/sdk/guides/skill), [hooks](https://docs.openhands.dev/sdk/guides/hooks), [custom condensers](https://docs.openhands.dev/sdk/arch/condenser), [browser and computer use](https://docs.openhands.dev/sdk/guides/computer-use), evaluation against benchmarks. Each one is another knob in `harness.py` waiting for a reason to turn it.
- **Your own harness decisions.** You can now look at any agent product and ask concrete questions. Which model is it using? What tools does it expose? What does it remember? What can it break? Where does the loop stop? If you can answer those for your own `harness.py`, you can answer them for anything.
