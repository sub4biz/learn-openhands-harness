# Dynamic Workflow Decision Rule

Use dynamic workflows when the target determines the plan.

## Good fit

- Large code review where each file or concern can be checked independently.
- Migration planning where affected surfaces are discovered during inspection.
- Release readiness or security audit where independent reviewers can verify each other.
- Research task where the right angles are not known before the first pass.

## Poor fit

- A deterministic deployment, compliance, or approval sequence.
- A small bug fix where one agent can hold the whole context.
- A task where every sub-agent would reread the same files.
- A task where the final answer cannot be checked with tests, citations, or a rubric.

## Harness rule

Keep these in code:

- available tools
- registered sub-agent roles
- sandbox and safety policy
- max reviewer count
- artifact paths
- output rubric

Move these into the skill and model-authored workflow:

- which dimensions to review
- how to phrase each reviewer prompt
- which independent checks can run in parallel
- how to preserve caveats during synthesis

Dynamic workflows reduce orchestration code only when the skill is tight enough that the generated workflow is debuggable from the trace.
