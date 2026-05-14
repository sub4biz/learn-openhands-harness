# P03: Retrieval

| | |
|---|---|
| **What You Do** | Run the prompt with `terminal + file_editor` only, then with an MCP code-search server attached. Measure when the extra retrieval tool earns its slot vs when it just adds turns. |
| **Harness Mechanism** | Lexical baseline (`grep` / file reads / `find`) vs. lexical + [MCP](https://docs.openhands.dev/sdk/guides/mcp) `search_code` |

**Phase: STOP HALLUCINATED PATHS.** Coding agents default to `grep`. The [talk + slides](https://github.com/rajshah4/harness-engineering#presentation-materials) frame the retrieval decision around vocabulary mismatch: semantic search only earns its slot when lexical search cannot bridge the gap.

## Directory guide

| Directory | What's inside |
|---|---|
| `code_search_mcp.py` | Minimal dependency-free stdio MCP server with one `search_code` tool. It indexes the target repo and returns ranked snippets. |
| `starter/` | `run_retrieval.py`. Runs the default lexical tool set and includes the helper that builds the MCP config. |
| `solution/` | `run_retrieval.py`. Runs lexical-only and lexical+MCP configs and compares event/cost/MCP-call counts. Plus `mcp_decision_rule.md`, the one-line decision rule to keep. |

## Setup

- Same model (from P02), same baseline tool list. Hold them constant.
- Two configurations:
  - **A: lexical only:** `terminal` + `file_editor`.
  - **B: lexical + MCP search:** attach the included stdio MCP server through `Agent(..., mcp_config={"mcpServers": ...})`. It exposes `search_code` against the same repo.

If you use Dockerized Agent Canvas, the MCP command runs inside the agent-server container. Keep both this tutorial repo and the target repo under the mounted project root, for example:

```bash
export PROJECT_PATH=/Users/you/Code
export WORKSPACE_DIR=/projects/agent-canvas
```

The project scripts map this tutorial's `code_search_mcp.py` to `/projects/learn-openhands-harness/projects/p03-retrieval/code_search_mcp.py` before sending the config to the server.

Before spending model budget, smoke-test the MCP server:

```bash
uv run --with openhands-sdk --with openhands-tools \
  python projects/p03-retrieval/solution/run_retrieval.py --mcp-smoke
```

To verify the remote agent server can launch the MCP subprocess, run one short live check:

```bash
uv run --with openhands-sdk --with openhands-tools \
  python projects/p03-retrieval/solution/run_retrieval.py --mcp-live-smoke
```

That command should print `MCP` as `1` or more.

## Procedure

1. Run the exact prompt against config A. Note: how many `terminal` / `grep` calls, how many file reads, did it find the answer?
2. Run the synonym prompt against config A: `"How does the canvas pick which backend to talk to?"`
3. Run the synonym prompt against config B. Note the same plus how many `search_code` calls, and whether the agent actually *uses* the new tool or sticks with `grep`.

## What to look for

- For a repo where the query and source share vocabulary (`VITE_BACKEND_HOST` is mentioned by exact name), `grep` wins on latency and accuracy. Semantic adds turns without adding answers.
- Switch the prompt to something with a synonym gap (`"how does the canvas pick which backend to talk to"`). A strong flagship may still recover by grepping adjacent terms like `backend` and `proxy`; that is useful data, not a failure of the lesson.
- MCP earns its slot only when `search_code` reduces misses or avoids expensive wandering. If the MCP-call column is zero, the model did not need or choose the tool. This server is intentionally small: BM25-style scoring plus a few synonym expansions, not an embeddings service.

> Connection to the [talk + slides](https://github.com/rajshah4/harness-engineering#presentation-materials): fast lexical search is the baseline, and embeddings earn their keep only when they reduce misses or expensive wandering. Don't take this on faith. Measure on *your* repo.

In one live run on `agent-canvas`, lexical exact took 46 events / 91.5s / $0.25, while lexical synonym took 42 events / 58.8s / $0.17. That result supports the default rule: strong models often bridge small vocabulary gaps without extra retrieval infrastructure.

## What you keep

A one-line decision rule. Something like *"Enable MCP semantic search only when at least 30% of recent prompts contain query terms that don't appear in source."* Or: *"Lexical only for this repo, synonym gap is rare."* Either is a useful artifact. See `solution/mcp_decision_rule.md`.

-> Next: [P04: Task Decomposition](../p04-decomposition/)
