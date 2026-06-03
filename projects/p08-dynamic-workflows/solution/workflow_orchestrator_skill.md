# Workflow Orchestrator Skill

Use this skill when a user asks for a review, audit, research pass, migration plan, or release assessment whose useful subparts are not known until the target is inspected.

## When to use a dynamic workflow

Use a workflow when all of these are true:

- The task has 3 to 6 independent angles that can be explored separately.
- The best angles depend on the target file, repository, diff, or prompt.
- A final synthesis step can combine findings without hiding uncertainty.
- The harness can verify the output with a rubric, tests, or exact citations.

Do not use a workflow when the task is tiny, compliance-critical, destructive, or better represented by deterministic application code.

## Workflow shape

1. Inspect the target enough to choose review dimensions.
2. Build 3 to 5 review specs. Each spec must include:
   - `name`
   - `focus`
   - `evidence_required`
   - `failure_mode`
3. Fan out review specs to bounded sub-agents.
4. Reduce the findings into one report.
5. Verify the report before returning.

## Hard limits

- Do not edit the reviewed source file.
- Do not read `.env` or print secret values.
- Do not make network calls.
- Use at most 5 reviewer sub-agents.
- Require exact file paths and line references for findings.
- Preserve uncertainty from individual reviewers.
- Write a final report and a workflow summary artifact.

## Expected artifacts

Write these files under `.harness_workflow/dynamic/`:

- `REVIEW.md`: the synthesized review.
- `WORKFLOW_SUMMARY.md`: the chosen review dimensions, sub-agents used, evidence checked, and any limits hit.

## Suggested workflow API usage

Use the workflow tool's map/reduce pattern:

```python
review_results = await wf.map_agents(
    items=review_specs,
    prompt="Review {item[name]} for {item[focus]}. Cite exact paths and lines.",
    subagent_type="code_reviewer",
)

final_report = await wf.reduce_agent(
    items=review_results,
    prompt="Synthesize these independent reviews into REVIEW.md and WORKFLOW_SUMMARY.md.",
    subagent_type="review_synthesizer",
)
```

The model may choose the review dimensions, but it may not ignore the hard limits or artifact contract.
