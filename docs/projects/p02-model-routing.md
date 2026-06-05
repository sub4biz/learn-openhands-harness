# P02: Model Routing

## What You Do

Run the same prompt three ways: flagship model, small model, and a routed config. Compare turns, tokens, cost, and correctness.

## Harness Mechanism

Remote-safe model selection before agent construction, with `LLMRegistry` as the larger-harness pattern.

## Open First

- [`projects/p02-model-routing/README.md`](https://github.com/rajshah4/learn-openhands-harness/blob/main/projects/p02-model-routing/README.md)
- [`starter/`](https://github.com/rajshah4/learn-openhands-harness/tree/main/projects/p02-model-routing/starter)
- [`solution/`](https://github.com/rajshah4/learn-openhands-harness/tree/main/projects/p02-model-routing/solution)

## Keep

A small routing policy: routine text and code-search prompts can use a cheaper model, while security, architecture, image, or multi-file tasks route up.

P09 returns to model routing as a full benchmark with `RouterLLM`, profiles, `SwitchLLMTool`, Laminar traces, and cost per solved task.
