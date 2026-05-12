# 2 — Harness Tour: One Task, Five Moving Parts

A coding agent is not just a model. It's a model wrapped in a **harness** — the code that decides which model to call, what tools it can use, what it remembers, how the loop runs, and where the work happens. Every coding-agent product (Claude Code, Codex CLI, Cursor, OpenHands) ships a harness. The difference is whether you can see it.

In this tour you'll give the agent a real task, watch it work, and then walk through the trace to see each part of the harness in action. By the end, you'll know what a harness is made of — and what the [projects](./projects/) will have you change.

> **Prerequisites:** a running agent server and canvas from the [quickstart](./01-quickstart.md), and the `agent-canvas` repo cloned locally.

---

## 2.1 Give it a real task

You just set up the agent-canvas project in the quickstart. The canvas frontend needs to know where the backend server lives — that's controlled by an environment variable called `VITE_BACKEND_HOST`. It gets read in frontend code, set in dev scripts, and overridden in different configurations. Understanding how that wiring works is a real question a developer would ask when joining this project.

It's also a good harness test: the agent has to search across multiple files, read what it finds, connect the dots, and produce a written summary — without modifying anything. You'll reuse this same prompt across all six projects so you can compare how different harness configurations change the agent's behavior on the same task.

Open the canvas at `http://localhost:8000`. Start a new conversation and paste this prompt:

```
Find every place VITE_BACKEND_HOST is read or set in this project,
and write a short note explaining how the dev script picks the backend.
```

Watch the agent work. When it finishes, come back here.

---

## 2.2 Read the trace

Click into the conversation in the canvas. You'll see a list of events, top to bottom:

1. **Your message** — the prompt you sent.
2. **Tool calls** — the agent decided to run `terminal` (probably `grep -rn VITE_BACKEND_HOST`) or `file_editor` (to read a file).
3. **Tool results** — what came back from each tool call.
4. **More tool calls** — maybe it grepped, then read specific files, then grepped again.
5. **A final message** — the agent's written answer.

This sequence is the **agent trace**. It's the chronological record of everything the harness did — every decision, every tool call, every result. It's also what makes an open harness different from a closed one: you're not guessing what happened, you're reading it.

Count the events. Note what tools the agent used, how many times, and in what order. You'll compare this baseline against different harness configurations in the projects.

> The trace is built on OpenHands' [Event](https://docs.openhands.dev/sdk/arch/events) framework. Each row is one typed event. The SDK exposes the same data via `conversation.state.events`, and `conversation.conversation_stats.get_combined_metrics()` gives you token counts and cost.

---

## 2.3 Part 1 — The model

Somewhere in that trace, an LLM read the context and decided what to do next. Which model was it?

If you used the canvas defaults, it's whatever you configured in the model picker. If you ran `quickstart.py`, it's the `LLM_MODEL` you exported (or the Sonnet 4.5 default). Either way, one model did all the work — reasoning, tool selection, and writing the answer.

That's fine for a first run. But it's also the most expensive configuration. In a real harness, you might want:

- A **cheap model** for simple tasks (title generation, quick lookups).
- A **flagship model** for hard reasoning.
- A **router** that picks between them per-call based on complexity or content.

OpenHands supports all three through `LLM`, [`LLMRegistry`](https://docs.openhands.dev/sdk/guides/llm-registry), and [`RouterLLM`](https://docs.openhands.dev/sdk/guides/llm-routing). [P02](./projects/p02-model-routing/) has you wire up a router and compare the cost.

**The point:** the model is one part of the harness. Swapping it changes cost and capability, but the rest of the harness — tools, memory, safety, architecture — stays the same. That separation is what makes the harness tunable.

---

## 2.4 Part 2 — The tools (retrieval)

Look at the tool calls in your trace. The agent probably used:

- **`terminal`** — to run `grep`, `find`, or `rg` in the shell. This is lexical search: exact string matching across files.
- **`file_editor`** — to read specific files it found interesting.
- Maybe **`task_tracker`** — to write down what it found so far.

That's it. No vector database, no embeddings, no RAG pipeline. The agent found code by grepping for it, the same way you would. For exact symbol names like `VITE_BACKEND_HOST`, grep is fast and reliable.

But what if the prompt had been vaguer — "How does the canvas pick which backend to talk to?" Same question, different words. Grep for `VITE_BACKEND_HOST` won't work if you don't know that name yet. That's the vocabulary-mismatch problem, and it's when semantic search (via [MCP](https://docs.openhands.dev/sdk/guides/mcp)) earns its place in the tool list.

The tools the agent can use are set when the conversation starts. You choose them:

```python
agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),    # grep, find, shell commands
        Tool(name=FileEditorTool.name),  # read and edit files
    ],
)
```

Add a tool, and the agent can reach for it. Remove one, and it can't. The tool list is the harness deciding what kind of retrieval the agent is allowed to do. [P03](./projects/p03-retrieval/) has you compare lexical-only against lexical + semantic.

---

## 2.5 Part 3 — Memory

Now ask: what did the agent know about this repo before it started searching?

Nothing. It had your prompt, the system prompt the harness assembled, and the tools. It had to discover the project structure, the file layout, and the conventions from scratch — by grepping and reading.

That's expensive. If this were a repo you work in every day, you'd want the agent to start with some context: "this is a monorepo, the frontend is in `apps/canvas`, the backend is in `apps/server`, config lives in `.env` files." That's what **`AGENTS.md`** does — a small file at the repo root that the harness reads at conversation start and injects into the system prompt.

Memory in a harness has three layers:

| Layer | What it is | OpenHands surface |
|---|---|---|
| **Active context** | The system prompt + recent events the model can see right now | Managed by [condensers](https://docs.openhands.dev/sdk/arch/condenser) — when context gets too long, older events are summarized or dropped. You can see compaction events in the trace. |
| **Working state** | Files the agent creates during a run — plans, notes, partial outputs | The workspace filesystem. The agent reads them back with `file_editor` or `terminal`. |
| **Durable memory** | Knowledge that persists across conversations | [`AGENTS.md`](https://docs.openhands.dev) at the repo root, plus [skills](https://docs.openhands.dev/sdk/guides/skill) loaded on demand. |

Check your trace: did a compaction event fire? On a short task, probably not. On a longer one, you'd see older events replaced by a summary — that's the condenser protecting the context window.

[P04](./projects/p04-memory/) has you run the same task with and without an `AGENTS.md` and measure the difference. A few lines of hand-written context can save the agent several rounds of exploratory grepping.

---

## 2.6 Part 4 — Safety and the loop

The agent ran shell commands on your machine. It could have run `rm -rf`. It could have run `git push`. It could have curled a URL and exfiltrated your source code. Right now, nothing in the harness stopped it.

That's fine for a tutorial on a scratch repo. It's not fine for real work. The harness needs to answer: what is the agent allowed to do automatically, what needs your approval, and what should never run?

OpenHands gives you three layers for this:

- **A security policy** — a template file (`org_security_policy.j2`) that tells the model what's LOW, MEDIUM, and HIGH risk. This guides the model's own judgment but doesn't enforce anything by itself.
- **Security analyzers** — code that classifies each proposed action. Deterministic analyzers catch known dangerous patterns; an LLM-based analyzer handles the gray areas. Compose them with `EnsembleSecurityAnalyzer`.
- **A confirmation policy** — `ConfirmRisky()` pauses the loop when the analyzer flags something above a threshold. `AlwaysConfirm()` requires approval for every action. The canvas surfaces these pauses for you to approve or reject.

Together, these turn the agent loop from "run everything blindly" into "run safe things, ask about risky things, block dangerous things." The loop itself — `Conversation.run()` — is where this all executes: build prompt → call LLM → propose action → classify risk → run or pause → ingest result → repeat.

The loop also has a [stuck detector](https://docs.openhands.dev/sdk/guides/agent-stuck-detector) that watches for the agent repeating the same failed action, and [hooks](https://docs.openhands.dev/sdk/guides/hooks) where you can inject custom logic at each step.

[P05](./projects/p05-safety/) has you wire up a security analyzer, a confirmation policy, and a Docker sandbox. That's where the harness goes from "learning tool" to something you'd trust with a real repo.

---

## 2.7 Part 5 — Architecture (where it runs)

Your agent ran as a single process on your laptop, with direct access to your filesystem. That's one architecture. There are others:

| Shape | What it means | When to use |
|---|---|---|
| **Local subprocess** | The agent server runs on your machine. Full filesystem access. | Learning, scratch work, trusted read-only exploration. What `npm run dev:dangerously-dockerless` gives you. |
| **[Docker sandbox](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)** | The agent server runs in a container. Isolated filesystem and network. | Real work on real repos. Kill the container and everything resets. |
| **[Cloud workspace](https://docs.openhands.dev/sdk/guides/agent-server/cloud-workspace)** | A hosted runtime — no local Docker needed. | Managed isolation, team use, CI integration. |

Switching from local to Docker is a one-line change in your Python code — swap `Workspace(...)` for `DockerWorkspace(...)`. The agent code, tools, prompts, and trace stay identical. That's the harness boundary: *where* the work runs is separate from *how* it runs.

There's also a "how many agents" axis. Your task ran as a single agent. For harder tasks, you might want:

- **[Sub-agent delegation](https://docs.openhands.dev/sdk/guides/agent-delegation)** — spawn a child agent for a bounded subtask.
- **A [critic](https://docs.openhands.dev/sdk/guides/critic)** — a second LLM that reviews the first agent's work.

Default to single. Multi-agent adds coordination cost that has to earn itself. [P06](./projects/p06-capstone/) is where you optionally add a critic.

---

## 2.8 The harness, all together

Here's what you just saw, labeled:

```
┌─────────────────────────────────────────────────┐
│                   THE HARNESS                    │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Model   │  │  Tools   │  │    Memory      │  │
│  │          │  │          │  │                │  │
│  │ Sonnet   │  │ terminal │  │ AGENTS.md      │  │
│  │ or cheap │  │ file_ed  │  │ condensers     │  │
│  │ or route │  │ +MCP?    │  │ workspace      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                  │
│  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  Loop + Safety   │  │    Architecture      │  │
│  │                  │  │                      │  │
│  │ security policy  │  │ local / Docker /     │  │
│  │ analyzers        │  │ cloud                │  │
│  │ confirmation     │  │ single / multi-agent │  │
│  │ stuck detector   │  │                      │  │
│  └──────────────────┘  └──────────────────────┘  │
│                                                  │
└─────────────────────────────────────────────────┘
```

Every coding agent has these parts, whether or not the product lets you see them. Claude Code has a model, tools, memory, a loop, and an architecture — you just can't inspect or change most of it. OpenHands exposes all five, which is why it works for learning what a harness actually is.

The power of understanding the harness: when an agent fails, you stop asking "is the model bad?" and start asking "which part of the harness should I change?" Maybe the model is fine but the tools are wrong. Maybe the tools are fine but the agent had no memory of the repo. Maybe everything is fine but the agent ran too long without a stuck detector. The trace tells you which part broke.

---

## 2.9 What's next

The [projects](./projects/) take each of these five parts and have you change it, measure the difference, and keep the configuration that works. By P06, you'll have a complete `harness.py` that wires together your model routing, tool selection, memory policy, security profile, and sandbox — built from the parts you just saw in action.

| Project | What you change | What you learn |
|---|---|---|
| [P01 — Agent Trace](./projects/p01-agent-trace/) | Nothing — you read the trace | How to diagnose what the harness did |
| [P02 — Model Routing](./projects/p02-model-routing/) | The model | Cost vs. capability tradeoffs |
| [P03 — Retrieval](./projects/p03-retrieval/) | The tools | When semantic search earns its slot |
| [P04 — Memory](./projects/p04-memory/) | `AGENTS.md` and condensers | How prior knowledge changes behavior |
| [P05 — Safety](./projects/p05-safety/) | Security policy + Docker | Bounding what the agent can do |
| [P06 — Capstone](./projects/p06-capstone/) | Everything, wired together | A production-shaped harness |
