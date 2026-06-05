# Copy-Ready Artifacts

These are the artifacts worth pulling out of the project solutions into a future standalone library.

## Agent Operation

- `AGENTS.md`: repo context, conventions, and definition of done.
- trace checklist: event fields to record for every run.
- run result table: model, tools, tokens, cost, pass/fail, and notes.

## Evaluation

- critic rubric: correctness, verification, scope, reliability, maintainability, and handoff readiness.
- cost-per-solved-task table: especially for routing and escalation experiments.
- repeated-run template: same prompt, same repo, multiple harness configurations.

## Safety

- org security policy.
- confirmation threshold.
- Docker workspace runner.
- risky-action examples for dry classification.

## Routing

- static routing rules.
- risk floor rules.
- escalation triggers.
- profile names for `SwitchLLMTool`.
- Laminar trace tags.

## Suggested Library Shape

```text
library/
├── AGENTS.md
├── trace-checklist.md
├── run-results-template.md
├── critic-rubric.md
├── org-security-policy.j2
├── routing-policy.md
└── escalation-policy.md
```
