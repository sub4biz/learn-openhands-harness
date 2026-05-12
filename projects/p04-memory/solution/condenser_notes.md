# Condenser / Memory Policy Notes

## Observations from P04 runs

### AGENTS.md effect
- With a minimal hand-written AGENTS.md (5-10 lines), the agent skipped N re-discovery turns.
- Auto-generated AGENTS.md (if tested) was [better/worse/same] — consistent with the ETH Zurich finding that human-written context outperforms auto-generated.

### Compaction
- Compaction [did/did not] fire during these runs.
- If it fired: the synthetic summary preserved [what?] and lost [what?].
- If it didn't fire: the task was short enough to fit in the context window without compression.

### Policy decisions
- **AGENTS.md**: hand-written, 5-20 lines, focused on directory layout and non-obvious conventions.
- **Skills**: [none kept / skill X kept because it demonstrably reduced turns on Y-type prompts].
- **Compaction**: trust the default condenser for now; audit the summary event when runs get longer.

## References
- [OpenHands condenser architecture](https://docs.openhands.dev/sdk/arch/condenser)
- [ETH Zurich: auto-generated vs. human instructions](https://arxiv.org/abs/2510.02669)
- [rajshah4/evaluating-skills-tutorial](https://github.com/rajshah4/evaluating-skills-tutorial)
