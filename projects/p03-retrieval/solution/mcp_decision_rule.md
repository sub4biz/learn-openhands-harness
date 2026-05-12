# MCP Decision Rule

> **Enable MCP semantic search only when the agent consistently fails to find answers via `grep` / `find` / file reads — i.e., when query terms don't appear verbatim in source.**

For most code-reading tasks where the prompt uses the same vocabulary as the source (function names, variable names, config keys), lexical tools win on latency and accuracy. Semantic adds turns without adding answers.

Switch to semantic when:
- 30%+ of recent prompts use natural-language descriptions rather than exact identifiers
- The codebase uses non-obvious naming conventions
- Cross-language or cross-file concept lookup is needed

Default for this repo: **lexical only — synonym gap is rare.**
