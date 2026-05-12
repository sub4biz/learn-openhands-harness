# Trace-Reading Checklist

Use this checklist every time you read an agent trace. It applies to canvas traces, SDK traces, and `/api/conversations/{id}/events/search` API responses.

## For every trace

- [ ] **User message present** — the prompt that started this run
- [ ] **Tool calls identified** — each tool call has a name, input, and matching observation
- [ ] **Observation quality** — tool outputs are concrete (file contents, grep results), not hallucinated
- [ ] **Final answer grounded** — cites real files/lines from the observations, not invented paths
- [ ] **Turn count reasonable** — for a code-reading task on a ~100-file repo, 3-8 tool calls is healthy; 20+ is a retrieval problem

## Diagnosis triggers

- [ ] **First bad observation** — if the final answer is wrong, find the first observation that led the agent astray
- [ ] **Missed retrieval** — did the agent skip a grep or file read it should have done?
- [ ] **Redundant retrieval** — did the agent re-read the same file or re-run the same grep?
- [ ] **Compaction event** — did the context window get compacted? What was preserved vs. lost?
- [ ] **Tool schema enforcement** — any `str_replace` failures from non-unique matches? That's the schema doing its job.

## Comparison fields (fill in for every run)

| Field | Value |
|---|---|
| Repo + SHA | |
| Prompt | |
| Model | |
| Active tools | |
| Tool calls by type | |
| Files read | |
| Files edited | |
| Compaction fired? | |
| Wall-clock | |
| Cost | |
| Correct? | |
