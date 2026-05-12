# P04: Memory + Compaction

| | |
|---|---|
| **What You Do** | Compare no durable memory, minimal `AGENTS.md`, and optional skills. Then inspect whether compaction appears in the agent trace and what it preserved. |
| **Harness Mechanism** | `AGENTS.md` injection + [Skills](https://docs.openhands.dev/sdk/guides/skill) + [Condenser](https://docs.openhands.dev/sdk/arch/condenser) policy |

**Phase: REDUCE RE-DISCOVERY.** Memory done well saves turns. Memory done badly adds tokens to every prompt for no benefit.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_memory.py`. runs against a repo with no `AGENTS.md` and no condenser config. TODOs for adding memory. |
| `solution/` | `run_memory.py`. runs both configs (no memory vs. with `AGENTS.md`) and compares. Plus `AGENTS.md` (a sample for agent-canvas) and `condenser_notes.md` (policy notes to keep). |

## Setup

- Same model + tools + retrieval policy from P01-P03.
- Two configurations (and one optional):
  - **A: no `AGENTS.md`:** the scripts copy `WORKSPACE_DIR` to a temp directory and remove `AGENTS.md` there, so your original repo is not touched.
  - **B: minimal `AGENTS.md`:** three to five lines, hand-written, describing the directory layout and any non-obvious conventions. Don't auto-generate it.
  - **C (optional): auto-generated `AGENTS.md`:** let the agent write it itself in a previous conversation. Feed that one in.

## Procedure

1. Run the prompt against A. Record turns, tokens, correctness, and *what the agent re-discovered*: directory layout, where to look first, etc.
2. Add `AGENTS.md`, fresh conversation, same prompt. Compare.
3. (Optional) Run C. If the [ETH Zurich result](https://arxiv.org/abs/2510.02669) holds, C will be measurably worse than B.

## What to look for

- Useful `AGENTS.md` reduces re-discovery turns. Useless `AGENTS.md` (verbose, generic) just adds tokens to every prompt.
- This is the talk's slide-58/59 result, replicated on your repo. Worth doing yourself once.
- If compaction fires, inspect the synthetic summary event. A closed harness asks you to trust its memory compression; an open harness lets you audit what was kept and what was thrown away.

## Skills extension

Once `AGENTS.md` is dialed in, evaluate one skill the same way. Pick a skill from [`OpenHands/extensions`](https://github.com/OpenHands/extensions), enable it via `VITE_LOAD_PUBLIC_SKILLS=true`, and run with-skill vs. without-skill on a prompt where the skill should fire. The pattern is the same as [`rajshah4/evaluating-skills-tutorial`](https://github.com/rajshah4/evaluating-skills-tutorial); SkillsBench reports 16% of skills *reduce* performance, so don't trust them by default.

## What you keep

Your hand-written `AGENTS.md` (5-20 lines), a note on whether compaction fired and what it preserved, and *at most one* skill that demonstrably moved the needle. If no skill helped, keep none. See `solution/` for examples.

→ Next: [P05: Org Safety Profile](../p05-safety/)
