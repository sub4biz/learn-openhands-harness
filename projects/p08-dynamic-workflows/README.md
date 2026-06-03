# P08: Dynamic Workflows

| | |
|---|---|
| **What You Do** | Compare hard-coded orchestration against a workflow-capable harness where the model chooses the review dimensions, writes the fan-out/fan-in workflow, and returns one synthesized report. |
| **Harness Mechanism** | Workflow tool + model-authored orchestration + skills that constrain when and how the model may coordinate sub-agents |

**Phase: REDUCE ORCHESTRATION CODE.** P04 taught decomposition where your application code owns the sequence: docs check, setup check, safety check, aggregate. Dynamic workflows move more of that coordination into the model. You still own the harness contract: available tools, available sub-agent roles, safety limits, output schema, and evaluation. The model owns the short-lived workflow plan.

This is the larger pattern showing up across agent products. Claude Code's dynamic workflows let Claude break a large task into parallel subagents and coordinate the result. Cursor's skills and subagents push in the same direction: reusable procedure lives in model-readable files, and the agent decides when a skill or subagent fits the task. The OpenHands demo in [rajshah4/workflow-demos](https://github.com/rajshah4/workflow-demos) shows an open interpretation of the pattern using skills, registered sub-agents, and a workflow tool.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_dynamic_workflow.py` runs the manual code-review workflow and leaves TODOs for the dynamic workflow skill and workflow-tool wiring. |
| `solution/` | `run_dynamic_workflow.py` includes the manual comparison, an optional live workflow-tool path, `workflow_orchestrator_skill.md`, and `dynamic_workflow_decision_rule.md`. |

## Agent-assisted path

1. Open this `README.md` and `starter/` only.
2. Ask your coding agent to explain the ownership boundary: what remains in harness code, what moves into the skill, and what the model decides at runtime.
3. Ask it to complete the TODOs without reading `solution/`.
4. Require it to run the dry-run smoke check. Only run the live dynamic workflow if your SDK install includes workflow support.
5. Compare against `solution/` and write down what orchestration code disappeared, and what new guardrails became necessary.

## Before you run

Pause and predict:

- Which parts of a multi-expert review are stable enough to keep in code?
- Which parts should the model choose dynamically from the target file?
- What constraints must the skill include so "the model decides" does not mean "anything goes"?
- What trace evidence would prove the workflow is doing useful coordination rather than hiding work?
- How much extra cost would be acceptable if orchestration code gets simpler?

## Setup

The dry run uses only the Python standard library:

```bash
cd projects/p08-dynamic-workflows/solution
uv run python run_dynamic_workflow.py --dry-run --mode both
```

The manual live comparison uses the same remote Agent Server path as P01-P05:

```bash
WORKSPACE_DIR=/path/to/repo \
uv run --with openhands-sdk --with openhands-tools python run_dynamic_workflow.py --mode manual
```

The dynamic live path requires an OpenHands SDK build with `WorkflowToolSet`. At the time this lesson was added, the public demo pointed to OpenHands SDK PR #3426 for workflow support. If your installed SDK does not expose `openhands.tools.workflow`, the script exits with a clear message and the dry run still teaches the code-shape comparison.

```bash
WORKSPACE_DIR=/path/to/repo \
uv run --with openhands-sdk --with openhands-tools python run_dynamic_workflow.py --mode dynamic
```

Default target file:

```text
projects/_runtime.py
```

Override it with `--target path/to/file.py`. Relative paths are resolved inside the copied workspace.

## The comparison

Config A is the old way:

1. Your Python code names the reviewers.
2. Your Python code runs each reviewer prompt.
3. Your Python code decides when aggregation happens.
4. The model acts as a worker inside your fixed loop.

Config B is the dynamic workflow:

1. Your Python code registers available roles and gives the parent agent the workflow tool.
2. Your skill tells the model when workflows are appropriate, what limits apply, and what final artifacts must exist.
3. The model writes the short-lived workflow: which review dimensions, how many sub-agents, what prompts, and how to reduce results.
4. The trace and final report show whether that autonomy earned itself.

The point is not "dynamic is always better." The point is to move reusable policy into a skill, reduce repeated orchestration code, and then verify the result with the trace.

## What to look for

- Did the dynamic run choose review dimensions that match the actual target file?
- Did it stay inside the skill limits: no edits, no network, bounded reviewers, line-specific findings?
- Did the final report preserve uncertainty and per-reviewer evidence?
- Did the trace expose the generated workflow and sub-agent calls clearly enough to debug?
- Did orchestration code shrink, or did complexity move into an untestable prompt?
- Would a fixed P04-style sequence have been easier to reason about?

## What you keep

Two artifacts:

- `workflow_orchestrator_skill.md`: the reusable skill that teaches the model when and how to coordinate a dynamic workflow.
- `dynamic_workflow_decision_rule.md`: the rule for when dynamic workflows earn their complexity.

Good default decision rule:

> Use a dynamic workflow when the task has many independent angles, the exact angles depend on the target, parallel exploration is useful, and the harness can verify the output. Keep orchestration in code when the sequence is compliance-critical, tiny, or easier to test as deterministic control flow.

## Further reading

- [rajshah4/workflow-demos](https://github.com/rajshah4/workflow-demos), the OpenHands-oriented demo this lesson is based on.
- [Claude Code: Introducing dynamic workflows](https://claude.com/blog/introducing-dynamic-workflows-in-claude-code), the product pattern this demo interprets.
- [Cursor 2.4 changelog: Subagents, Skills, and Image Generation](https://cursor.com/changelog/2-4), showing the same shift toward model-selected skills and specialized subagents.

-> End of advanced path. Use the decision rule to decide whether dynamic workflows belong in your own `harness.py`.
