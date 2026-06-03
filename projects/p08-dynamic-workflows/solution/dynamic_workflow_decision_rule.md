# Dynamic Workflow Decision Rule

Use dynamic workflows when the question determines the plan.

## Good fit

- Deep research where the right angles are not known before inspection.
- Codebase-wide audits where independent agents can inspect different surfaces.
- Migration planning where affected areas are discovered during the first pass.
- High-stakes synthesis where independent verification should happen before the final answer.

## Poor fit

- A deterministic deployment, compliance, or approval sequence.
- A small question where one agent can hold the whole context.
- A task where every sub-agent would reread the same sources.
- A task where the final answer cannot be checked with tests, citations, source status, or a rubric.

## Harness rule

Keep these in code:

- available tools
- registered sub-agent roles
- sandbox and safety policy
- max fan-out
- artifact paths
- output rubric

Move these into the skill and model-authored workflow:

- which research angles to pursue
- how to phrase each research prompt
- which claims need verification
- which independent checks can run in parallel
- how to preserve caveats during synthesis

Dynamic workflows reduce orchestration code only when the skill is tight enough that the generated workflow is debuggable from the trace.
