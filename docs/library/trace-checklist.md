# Trace Checklist

Use this checklist after every live run. The trace is the unit of diagnosis.

## Run Metadata

| Field | Value |
|---|---|
| Repo and SHA | |
| Prompt | |
| Model | |
| Tool list | |
| Workspace type | |
| Started from Canvas or SDK | |

## Event Review

Record:

- first useful search or file read
- every tool type used
- files read
- files edited
- commands run
- confirmation events
- compaction events
- model switch events
- final answer

## Metrics

Record:

- total events
- turns
- input tokens
- output tokens
- accumulated cost
- wall time
- pass/fail
- cost per solved task, when comparing strategies

## Diagnosis Questions

- Did the agent retrieve the right evidence before answering?
- Did it repeat the same failed action?
- Did it edit before understanding?
- Did it verify with the right command?
- Did it stop too early?
- Did the harness expose enough information to explain the result?
