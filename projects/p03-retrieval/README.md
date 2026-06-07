# P03: Retrieval

## What Problem Are You Solving?

Coding agents already retrieve well with `grep`, `find`, and file reads. The question this lesson answers is whether adding a dedicated search tool earns its slot or just adds turns. The honest answer is often "no, `grep` wins," and that is a legitimate result.

You run the same task two ways and let the trace decide:

1. **Lexical only.** `terminal` + `file_editor`. The agent greps and reads files.
2. **Lexical plus MCP search.** The same tools plus a `search_code` MCP server over the same repo.

You compare on a vocabulary-match prompt (where the query words appear verbatim in the code) and a synonym prompt (where they do not), and ask whether `search_code` improved correctness, reduced misses, or shortened the path.

This is the mirror image of [P10: Indexing Agent History](../p10-history-index/). There, history is unbounded so you must index. Here, the codebase is bounded and `grep` is already excellent, so retrieval is a judgment call, not a given.

## Start With These Files

Open this README and `starter/` only. Ask your coding agent to complete the TODOs without reading `solution/`, smoke-test the MCP server, run the live check, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| The MCP server | `code_search_mcp.py` (dependency-free stdio server, one `search_code` tool, BM25-style ranking) | same |
| Run the configs | `starter/run_retrieval.py` (lexical + the MCP-config helper) | `solution/run_retrieval.py` (lexical vs lexical+MCP, compares events/cost/MCP calls) |
| The artifact to keep | | `solution/mcp_decision_rule.md` |

## The Two Configurations

Hold the model (from P02) and the baseline tool list constant. Only retrieval changes.

- **A: lexical only.** `terminal` + `file_editor`.
- **B: lexical plus MCP search.** Attach the included stdio server through `Agent(..., mcp_config={"mcpServers": ...})`, exposing `search_code` against the same repo.

If you use Dockerized Agent Canvas, the MCP command runs inside the agent-server container, so keep both this repo and the target repo under the mounted project root:

```bash
export PROJECT_PATH=/Users/you/Code
export WORKSPACE_DIR=/projects/agent-canvas
```

Before you run, predict. Should exact-symbol search for `VITE_BACKEND_HOST` and `VITE_BACKEND_BASE_URL` need MCP at all? What synonym prompt would expose a vocabulary gap? What trace evidence would show `search_code` earned its slot? If `search_code` is available but called zero times, what does that tell you?

## Run It And Collect Metrics

Smoke-test the server before spending model budget:

```bash
uv run --with openhands-sdk --with openhands-tools \
  python projects/p03-retrieval/solution/run_retrieval.py --mcp-smoke
```

Verify the remote agent server can launch the MCP subprocess (should print `MCP` as 1 or more):

```bash
uv run --with openhands-sdk --with openhands-tools \
  python projects/p03-retrieval/solution/run_retrieval.py --mcp-live-smoke
```

Then run three passes:

1. Exact prompt against config A. Count `terminal`/`grep` calls and file reads; did it find the answer?
2. Synonym prompt against config A: `"How does the canvas pick which backend to talk to?"`
3. Synonym prompt against config B. Same counts, plus how many `search_code` calls, and whether the agent actually uses the tool or sticks with `grep`.

## Record The Results

| Run | Events | grep / reads | search_code calls | Wall | Cost | Found it? |
|---|---:|---:|---:|---:|---:|:--:|
| A exact | | | n/a | | | |
| A synonym | | | n/a | | | |
| B synonym | | | | | | |

For reference, one live run on `agent-canvas` showed lexical-exact at 46 events / 91.5s / $0.25 and lexical-synonym at 42 events / 58.8s / $0.17, which supports the default rule below: a strong model often bridges small vocabulary gaps without extra retrieval infrastructure.

## How To Read The Results

- When the query and source share vocabulary (`VITE_BACKEND_HOST` is named verbatim), `grep` wins on latency and accuracy. Semantic search just adds turns.
- On a synonym gap, a strong flagship may still recover by grepping adjacent terms like `backend` and `proxy`. That is useful data, not a failure of the lesson.
- MCP earns its slot only when `search_code` improves correctness, reduces misses, or avoids expensive wandering. A zero in the `search_code` column means the model did not need or choose the tool. This server is intentionally small (BM25-style scoring plus a few synonym expansions), not an embeddings service.

The point is to write the rule from evidence on your repo, not to assume the fancier tool is better.

<details>
<summary>References</summary>

- [MCP in OpenHands](https://docs.openhands.dev/sdk/guides/mcp): attaching a stdio MCP server through `mcp_config`.
- [P10: Indexing Agent History](../p10-history-index/): the case where retrieval is not optional.
- [Harness engineering talk and slides](https://github.com/rajshah4/harness-engineering#presentation-materials): retrieval as a speed/quality tradeoff.

</details>

## What Students Should Leave With

A one-line decision rule, written from your traces. For example: *"Enable MCP search only when trace comparisons show it improves correctness or lowers events/wall-clock on vocabulary-mismatch prompts,"* or *"Lexical only for this repo; synonym gaps are rare."* Either is a useful artifact. See `solution/mcp_decision_rule.md`.

Next: [P04: Task Decomposition](../p04-decomposition/)
