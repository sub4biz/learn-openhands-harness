# MCP Decision Rule

> **Enable MCP semantic search only when the agent consistently fails to find answers via `grep` / `find` / file reads — i.e., when query terms don't appear verbatim in source.**

For most code-reading tasks where the prompt uses the same vocabulary as the source (function names, variable names, config keys), lexical tools win on latency and accuracy. Semantic adds turns without adding answers.

The included `code_search_mcp.py` server is useful as a cheap probe: keep it available for experiments, but do not enable it by default unless the trace shows a real retrieval miss. In a live `agent-canvas` run, the synonym prompt was faster and cheaper with lexical tools alone, so the right conclusion was not "MCP everywhere"; it was "MCP only when the repo actually has a vocabulary-gap problem."

Switch to semantic when:
- 30%+ of recent prompts use natural-language descriptions rather than exact identifiers
- The codebase uses non-obvious naming conventions
- Cross-language or cross-file concept lookup is needed

Default for this repo: **lexical only — synonym gap is rare.**
