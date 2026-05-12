# Decomposition Plan

Use decomposition when the task has independent checks that can be scored or retried separately.

## Large Task

Review a repo for release readiness and produce `RELEASE_READINESS.md`.

## Monolithic Config

One agent run handles:

- documentation accuracy
- setup and test commands
- secret and environment handling
- safety warnings
- project structure
- final prioritization

## Decomposed Config

Run these scoped checks first:

| Step | Output |
|---|---|
| Docs check | `.harness_review/docs.md` |
| Setup/test check | `.harness_review/setup.md` |
| Secrets/safety check | `.harness_review/safety.md` |
| Project-structure check | `.harness_review/projects.md` |
| Final aggregation | `RELEASE_READINESS.md` |

## Evaluation Layer

Score both final reports against `evaluation_rubric.md`.

The most useful failure mode is not "the monolithic run crashed." It is:

> The monolithic run produced a confident report, but missed blocker categories
> that the decomposed checks found.

Also check report integrity. A decomposed aggregate can still make mistakes, such
as saying the summary contains 10 P0 issues while the P0 table lists a different
number. Decomposition improves coverage, but it still needs verification.

## Rule Of Thumb

Break down the work when:

- the task has separable dimensions
- each dimension can cite exact files
- partial failure is useful
- retries can target one failed dimension

Keep it monolithic when:

- the answer depends on one shared chain of reasoning
- decomposed prompts would duplicate most context
- aggregation would hide important nuance
