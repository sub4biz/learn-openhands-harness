# P03: Retrieval

| | |
|---|---|
| **What You Do** | Run the prompt with `terminal + file_editor` only, then with an MCP semantic-search server attached. Measure when semantic earns its slot vs when it just adds turns. |
| **Harness Mechanism** | Lexical baseline (`grep` / file reads / `find`) vs. lexical + [MCP](https://docs.openhands.dev/sdk/guides/mcp) semantic |

**Phase: STOP HALLUCINATED PATHS.** Coding agents default to `grep`. The talk's stance (slides 25–31): semantic only earns its slot when you have a vocabulary mismatch.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_retrieval.py`. runs with the default lexical tool set. TODO for adding an MCP semantic-search server. |
| `solution/` | `run_retrieval.py`. runs both configs (lexical-only and lexical+MCP) and compares tool-call counts. Plus `mcp_decision_rule.md`. the one-line decision rule to keep. |

## Setup

- Same model (from P02), same baseline tool list. Hold them constant.
- Two configurations:
  - **A: lexical only:** `terminal` + `file_editor`.
  - **B: lexical + semantic:** add an MCP server through `Agent(..., mcp_config={"mcpServers": ...})` that exposes a `search_code` tool against the same repo. A small, real one is [`OpenHands/extensions`](https://github.com/OpenHands/extensions), or build or build a stub that wraps `bm25s` over the repo files.

## Procedure

1. Run the prompt against config A. Note: how many `terminal` / `grep` calls, how many file reads, did it find the answer?
2. Run against config B. Note the same plus how many `search_code` calls, and whether the agent actually *uses* the new tool or sticks with `grep`.

## What to look for

- For a repo where the query and source share vocabulary (`VITE_BACKEND_HOST` is mentioned by exact name), `grep` wins on latency and accuracy. Semantic adds turns without adding answers.
- Switch the prompt to something with a synonym gap (`"how does the canvas pick which backend to talk to"`) and the math can flip. Run that version too if you have budget; the contrast is the point.

> Connection to the talk: slide 27 (BM25 makes grep instant) and slides 29-31 (when embeddings earn their keep). Don't take this on faith. Measure on *your* repo.

## What you keep

A one-line decision rule. Something like *"Enable MCP semantic search only when at least 30% of recent prompts contain query terms that don't appear in source."* Or: *"Lexical only for this repo, synonym gap is rare."* Either is a useful artifact. See `solution/mcp_decision_rule.md`.

→ Next: [P04: Memory + Compaction](../p04-memory/)
