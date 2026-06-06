# Why OpenHands?

Closed agent products can be excellent, but they are hard to study. If the behavior changes, you may not know whether the model, prompt, tool policy, memory, safety layer, or runtime changed.

OpenHands is useful for learning because it is open source, so the harness is visible.

## What You Can Inspect

| Surface | What it teaches |
|---|---|
| Agent Server | The loop, workspace, events, tools, and API boundary |
| Agent Canvas | The operator view of messages, tool calls, approvals, and model switches |
| SDK | The programmable harness surface |
| Event trace | The chronological record of what happened |
| Metrics | Tokens, cost, and run statistics |
| Workspace | Where files, commands, and artifacts live |

## Why It Matters

The course is not only about OpenHands. It applies to any coding agent harness. We are using OpenHands to make general harness engineering concrete.

When a run fails, you can ask:

- Did the model have enough context?
- Did it have the right tools?
- Did the safety policy block or allow the right actions?
- Did memory reduce re-discovery?
- Did routing choose the right model?
- Did the critic or tests catch false completion?
- Did the trace expose the first bad step?

Those questions transfer to any coding agent product.
