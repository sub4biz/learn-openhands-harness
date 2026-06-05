# P09: Model Routing Benchmark

## What You Do

Run the same 10 coding tasks three ways: frontier-only, static rules routing, and cascading escalation. Compare pass rate, tokens, cost, and cost per solved task.

## Harness Mechanism

`RouterLLM`, `LLMProfileStore`, `SwitchLLMTool`, SDK metrics, Agent Canvas model-switch events, and Laminar traces.

## Open First

- [`projects/p09-model-routing-benchmark/README.md`](https://github.com/rajshah4/learn-openhands-harness/blob/main/projects/p09-model-routing-benchmark/README.md)
- [`starter/run_routing.py`](https://github.com/rajshah4/learn-openhands-harness/blob/main/projects/p09-model-routing-benchmark/starter/run_routing.py)
- [`starter/run_switch_cascade.py`](https://github.com/rajshah4/learn-openhands-harness/blob/main/projects/p09-model-routing-benchmark/starter/run_switch_cascade.py)
- [`solution/`](https://github.com/rajshah4/learn-openhands-harness/tree/main/projects/p09-model-routing-benchmark/solution)

## Keep

A routing benchmark table and escalation policy you can defend with traces and metrics.

The main lesson: use the cheapest model you trust, protect high-risk work with a risk floor, and escalate only when evidence says the current model is stuck.
