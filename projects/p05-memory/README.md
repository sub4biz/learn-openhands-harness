# P05: Memory + Compaction

## What Problem Are You Solving?

Memory done well saves turns by stopping the agent from re-discovering the same repo facts every run. Memory done badly adds tokens to every prompt for no benefit. This lesson measures which one you have.

You compare:

1. **No durable memory.** The agent rediscovers the repo from scratch.
2. **A minimal `AGENTS.md`.** Three to five hand-written lines of layout and non-obvious conventions.
3. **(Optional) An auto-generated `AGENTS.md`.** The agent wrote it itself in a prior run.

You also inspect whether compaction fires in the trace and what its synthetic summary preserved. A closed harness asks you to trust its memory compression; an open one lets you audit what was kept and what was thrown away.

## Start With These Files

Open this README and `starter/` only. Ask your coding agent to complete the TODOs without reading `solution/`, run the live command, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| Run both configs, save traces | `starter/run_memory.py` (no memory + TODOs) | `solution/run_memory.py` (both, saves trace JSON) |
| Compare saved traces offline | | `solution/compare_traces.py` |
| Artifacts | | `solution/AGENTS.md` (sample), `solution/condenser_notes.md` |

## The Configs

Hold the model, tools, and retrieval policy from P01 to P04 constant. The default target is your local `agent-canvas` checkout; the prompt and sample `AGENTS.md` are tuned for it.

```bash
export WORKSPACE_DIR=/path/to/your/projects/agent-canvas
```

The script copies `WORKSPACE_DIR` before each run and removes the root `AGENTS.md` only from the no-memory copy, so your real repo is never touched.

- **A: no `AGENTS.md`.**
- **B: minimal `AGENTS.md`.** Three to five lines, hand-written. Do not auto-generate it.
- **C (optional): auto-generated `AGENTS.md`.** Feed in one the agent wrote itself.

Before you run, predict. What repo facts belong in a minimal `AGENTS.md`? Which discovery steps should vanish when it is present? What token or event reduction would make it worth keeping? What would signal the memory is generic noise rather than useful context?

## Run It And Collect Metrics

From the solution directory:

```bash
WORKSPACE_DIR=/path/to/your/projects/agent-canvas \
uv run --with openhands-sdk --with openhands-tools python run_memory.py
```

Run the prompt against A and record turns, tokens, correctness, and what the agent re-discovered (directory layout, where to look first). Then add `AGENTS.md`, start a fresh conversation, same prompt. Optionally run C.

The runner prints two trace paths. Compare them without new model calls:

```bash
uv run python compare_traces.py \
  no-memory=/path/to/no-memory-events.json \
  with-memory=/path/to/with-memory-events.json
```

## Record The Results

| Config | Turns | Tokens | Re-discovery steps | Correct? |
|---|---:|---:|---:|:--:|
| A no memory | | | | |
| B minimal AGENTS.md | | | | |
| C auto-generated (optional) | | | | |

## How To Read The Results

- A useful `AGENTS.md` reduces re-discovery turns. A useless one (verbose, generic) just adds tokens to every prompt.
- `compare_traces.py` reports event deltas, token deltas, and a re-discovery proxy. Treat the proxy as a starting point, then read the raw trace before claiming why a run improved.
- If compaction fires, open the synthetic summary event and check what it kept versus discarded.
- If you run C, expect it to be measurably worse than B if the ETH Zurich result holds: a model writing its own context tends to bloat it.

Skills are the same experiment shape and not part of the main path: run without a skill, enable only that skill, rerun the same prompt, and keep it only if the trace shows a measurable gain. SkillsBench reports that some skills reduce performance, so do not trust them by default.

<details>
<summary>References</summary>

- [Condenser](https://docs.openhands.dev/sdk/arch/condenser): the compaction policy this lesson inspects.
- [ETH Zurich, self-written context](https://arxiv.org/abs/2510.02669): why auto-generated memory often underperforms a hand-written one.
- [Evaluating skills tutorial](https://github.com/rajshah4/evaluating-skills-tutorial): the same A/B rule applied to skills.

</details>

## What Students Should Leave With

Your hand-written `AGENTS.md` (5 to 20 lines), the `compare_traces.py` result, and a note on whether compaction fired and what it preserved. If you run a skill experiment later, keep only a skill that demonstrably moved the needle. See `solution/` for examples.

Next: [P06: Org Safety Profile](../p06-safety/)
