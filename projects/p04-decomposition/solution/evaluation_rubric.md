# P04 Evaluation Rubric

Use this rubric to compare the monolithic and decomposed `RELEASE_READINESS.md`
reports. The point is not whether the agent wrote a file. The point is whether
the report found the important failure modes.

## Expected Findings

| ID | Priority | Expected signal |
|---|---:|---|
| `agent_canvas_prereq` | P0 | Calls out `agent-canvas` as a required external repo/prerequisite when running the tutorial. |
| `agent_server_running` | P0 | Calls out that SDK scripts need a running agent server and should fail clearly if it is absent. |
| `api_key_validation` | P0 | Calls out weak or late `LLM_API_KEY` validation, including empty key risk. |
| `docker_requirement` | P0 | Calls out Docker/P06-P07 requirements or the real risk of dockerless host execution. |
| `correct_release_verdict` | P0 | Gives a not-ready/do-not-release verdict when blocking setup issues are present. |
| `safety_warning_prominence` | P1 | Checks whether dockerless safety warnings are prominent enough. |
| `project_title_consistency` | P1 | Checks project title, project name, and capitalization consistency. |
| `workspace_dir_default` | P1 | Checks ambiguous `WORKSPACE_DIR` or default working-directory behavior. |
| `dependency_clarity` | P1 | Checks whether per-project `uv --with ...` dependencies are documented clearly. |

## Report Integrity Check

The runner also checks whether the report's declared P0 count matches the number
of `P0-*` rows in its P0 table. This catches a common aggregation failure: the
summary claims one number, while the evidence table says another.

## How To Score Existing Reports

```bash
uv run python projects/p04-decomposition/solution/score_report.py \
  --score-report monolith=.openhands-runs/p04-decomposition/p04_monolith_xxxxxxxx/repo/RELEASE_READINESS.md \
  --score-report decomposed=.openhands-runs/p04-decomposition/p04_decomposed_xxxxxxxx/repo/RELEASE_READINESS.md
```

The scorer is intentionally simple. It looks for problem-framing language near
the expected topic, so a report that merely mentions `agent-canvas` or Docker
does not automatically get credit. Treat it as a repeatable teaching aid, not a
substitute for human review.
