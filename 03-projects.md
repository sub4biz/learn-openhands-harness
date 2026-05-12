# 3 — Six Projects (Learning Path)

Six small projects, in order, each changing one harness lever and producing a config artifact that carries forward. By P06 you'll have a runnable `harness.py` and an agent-trace evaluation record that wires together everything you kept — your trace-reading checklist, model routing, retrieval decision, memory policy, security profile, sandbox, and critic.

If you're using this as a first learning path, treat P01-P04 as the core concepts. P05-P06 are the advanced path where safety, verification, and composition start looking like production harness design.

The pattern is behavior first: decide what agent behavior you want, change the smallest harness surface that could affect it, then observe whether the trace changed.

> **Inspired by [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering)**, which organizes harness learning as a sequence of cumulative projects on the same Electron app rather than disconnected one-off ablations. That's a better shape for learning than the standard "here are some experiments" format, and it adapts naturally to OpenHands. The phase names, the two-column "What You Do / Harness Mechanism" preamble, and the "each project's solution becomes the next project's starter" property are all borrowed from there. Credit where it's due.

> **Common task across all projects.** Pick one repo and one prompt, and freeze them. A good default: clone [`OpenHands/agent-canvas`](https://github.com/OpenHands/agent-canvas) and use the prompt `"Find every place VITE_BACKEND_HOST is read or set, and write a short note explaining how the dev script picks the backend."` — narrow, repeatable, doesn't write code, and forces real retrieval.

---

## Project evolution

```text
PROJECT EVOLUTION (OpenHands harness)
=====================================

  P01  Canvas + agent trace          → SEE THE LOOP
       |                               keep: a baseline trace
       |                                     + trace-reading checklist
       v
  P02  Model routing                 → RIGHT-SIZE THE THINKING
       |                               keep: a RouterLLM / LLMRegistry config
       v
  P03  Retrieval                     → STOP HALLUCINATED PATHS
       |                               keep: a one-line decision rule
       |                                     for when MCP earns its slot
       v
  P04  Memory + compaction           → REDUCE RE-DISCOVERY
       |                               keep: a hand-written AGENTS.md
       |                                     + condenser/memory notes
       v
  P05  Org safety profile            → BOUND BLAST RADIUS
       |                               keep: org security profile
       |                                     + DockerWorkspace runner
       v
  P06  Verification + capstone       → STOP "LOOKS FINE"
                                       keep: Critic + rubric + harness.py

  Each project produces a concrete artifact.
  P06 is where they merge into one runnable harness.
```

Each project follows the same shape:

- A two-row preamble: **What You Do** / **Harness Mechanism**.
- Setup, procedure, and what to record.
- A **What you keep** callout at the end — the artifact that carries forward.

Use a fresh conversation per run. Save agent traces. Keep `results.md` next to your fork so the cumulative measurements line up.

---

## P01 — Canvas + Agent Trace

| | |
|---|---|
| **What You Do** | Run one narrow task through the canvas, then read the agent trace. Count tool calls, inspect observations, and save the trace as your baseline. |
| **Harness Mechanism** | Agent Server typed events + persisted conversation events + Canvas trace viewer |

**Phase: SEE THE LOOP.** Before changing any knobs, learn to read the loop. The differentiator here is not that the agent can call tools. Claude Code, Cursor, and OpenHands can all do that. The differentiator is that the harness trace is visible, queryable, forkable, and reusable as evaluation data.

**Setup:**
- Same repo and same prompt for the rest of the projects.
- Use the default canvas setup from the quickstart.
- Good default prompt: `"Find every place VITE_BACKEND_HOST is read or set, and write a short note explaining how the dev script picks the backend."`

**Procedure:**
1. Start a fresh conversation in the canvas and run the prompt to completion.
2. Open the agent trace. Identify: user message, assistant planning, each tool call, each observation, final answer, and any compaction placeholder.
3. Save the agent trace from `GET /api/conversations/{id}/events/search` or the canvas UI if export is available in your build. OpenHands stores the trace as typed events; "agent trace" is the teaching term.
4. Record the working directory, repo SHA, model, active tool list, number of tool calls, wall-clock time, cost, and whether the final answer cited real files.

**What to write down:**

| Trace field | Value |
|---|---|
| Repo + SHA | |
| Prompt | |
| Model | |
| Active tools | |
| Tool calls by type | |
| Files read | |
| Files edited | |
| Compaction fired? | |
| Final answer correct? | |

**What to look for:**
- The agent trace is the unit of diagnosis. If the final answer is wrong, find the first bad observation or skipped retrieval step.
- A healthy code-reading run has a small number of targeted searches and file reads before answering.
- A harness you cannot inspect cannot be tuned. This baseline trace is what makes the later ablations meaningful.

> **What you keep:** one baseline agent trace plus a trace-reading checklist. Every later project compares against this trace, not against vibes.

---

## P02 — Model Routing

| | |
|---|---|
| **What You Do** | Run the same prompt three ways: flagship LLM, small LLM, and a router that mixes them. Compare turns, tokens, cost, and where the cost lands. |
| **Harness Mechanism** | [`LLMRegistry`](https://docs.openhands.dev/sdk/guides/llm-registry) + [`RouterLLM`](https://docs.openhands.dev/sdk/guides/llm-routing) (e.g. `MultimodalRouter`) |

**Phase: RIGHT-SIZE THE THINKING.** Most operators leave the model lever untouched. This project changes that.

**Setup:**
- Same agent server, same canvas, same workspace.
- Same baseline trace fields from P01.
- Same prompt, same active tool list.
- Three configs:
  - **A — flagship:** e.g. `anthropic/claude-sonnet-4-5-20250929`.
  - **B — small:** e.g. `openai/gpt-5-mini-2025-08-07` or `anthropic/claude-haiku-4-5-20251001`.
  - **C — routed:** a `RouterLLM` (start with the shipped `MultimodalRouter`, or write a 20-line keyword router that sends `"refactor"` / `"design"` / `"debug complex"` to the flagship and everything else to the small model).

**Procedure:**
1. Start a conversation with config A. Run to completion. Record: turn count, in/out tokens *per `usage_id`*, accumulated cost, correctness.
2. Fork from start (or re-create) and run config B. Same metrics.
3. Run config C. Same metrics — but now `get_combined_metrics()` will break the cost down by leg of the router. Note which calls actually went to which model.

**What to write down:**

| Config | Turns | In tokens | Out tokens | Cost | Correct? | Where the cost landed |
|---|---|---|---|---|---|---|
| A flagship | | | | | | 100% flagship |
| B small | | | | | | 100% small |
| C routed | | | | | | _e.g. 20% flagship / 80% small_ |

**What to look for:**
- Turn-count differences across A and B are usually about *retrieval discipline* (does the model grep enough before guessing?), not raw intelligence. If the cheaper model uses fewer turns and gets the same answer, it's not because it's smarter — it's because the task didn't need the extra capability.
- Config C is the interesting one. If it lands within 10% of A's correctness at 30% of A's cost, you have evidence that *most of your task doesn't need the flagship*. If C drops sharply on correctness, your routing policy is sending the wrong things to the small model — fix the policy, not the models.

> Connection to the talk: slide 11 (same model, 2× gap from harness) and slide 22's framing of the model as *one of five levers, not the dominant one*. This is a personal-scale version of the [OpenHands Index](https://index.openhands.dev/home) experiment in [`experiments/model-specialization/`](../model-specialization/).

> **What you keep:** a `RouterLLM` or `LLMRegistry` configuration that lands within 10% of flagship correctness at 30–50% of flagship cost. Save the Python snippet (5–20 lines) verbatim. You'll paste it into `harness.py` in P06.

---

### Supporting note — tool surface and schema

Tool selection matters, but by itself it is not the differentiator. Claude Code, Cursor, and OpenHands all expose tool controls and MCP integrations. The interesting harness question is whether a tool's schema and runtime boundary make bad actions harder.

Keep this as a quick sanity check rather than a full project: compare a `terminal`-only run with the default `terminal + file_editor + task_tracker` run. If the shell-only agent overwrites files or loses context, write down the failure mode. The lesson is schema-enforced behavior, not "more tools."

---

## P03 — Retrieval

| | |
|---|---|
| **What You Do** | Run the prompt with `terminal + file_editor` only, then with an MCP semantic-search server attached. Measure when semantic earns its slot vs when it just adds turns. |
| **Harness Mechanism** | Lexical baseline (`grep` / file reads / `find`) vs. lexical + [MCP](https://docs.openhands.dev/sdk/guides/mcp) semantic |

**Phase: STOP HALLUCINATED PATHS.** Coding agents default to `grep`. The talk's stance (slides 25–31): semantic only earns its slot when you have a vocabulary mismatch.

**Setup:**
- Same model (from P02), same baseline tool list. Hold them constant.
- Two configurations:
  - **A — lexical only:** `terminal` + `file_editor`.
  - **B — lexical + semantic:** add an MCP server that exposes a `search_code` tool against the same repo. A small, real one is [`OpenHands/extensions`](https://github.com/OpenHands/extensions) — pick one or build a stub that wraps `bm25s` over the repo files.

**Procedure:**
1. Run the prompt against config A. Note: how many `terminal` / `grep` calls, how many file reads, did it find the answer?
2. Run against config B. Note the same plus how many `search_code` calls, and whether the agent actually *uses* the new tool or sticks with `grep`.

**What to look for:**
- For a repo where the query and source share vocabulary (`VITE_BACKEND_HOST` is mentioned by exact name), `grep` wins on latency and accuracy. Semantic adds turns without adding answers.
- Switch the prompt to something with a synonym gap (`"how does the canvas pick which backend to talk to"`) and the math can flip. Run that version too if you have budget; the contrast is the point.

> Connection to the talk: slide 27 (BM25 makes grep instant) and slides 29-31 (when embeddings earn their keep). Don't take this on faith — measure on *your* repo.

> **What you keep:** a one-line decision rule. Something like *"Enable MCP semantic search only when at least 30% of recent prompts contain query terms that don't appear in source."* Or: *"Lexical only for this repo — synonym gap is rare."* Either is a useful artifact.

---

## P04 — Memory + Compaction

| | |
|---|---|
| **What You Do** | Compare no durable memory, minimal `AGENTS.md`, and optional skills. Then inspect whether compaction appears in the agent trace and what it preserved. |
| **Harness Mechanism** | `AGENTS.md` injection + [Skills](https://docs.openhands.dev/sdk/guides/skill) + [Condenser](https://docs.openhands.dev/sdk/arch/condenser) policy |

**Phase: REDUCE RE-DISCOVERY.** Memory done well saves turns. Memory done badly adds tokens to every prompt for no benefit.

**Setup:**
- Same model + tools + retrieval policy from P01-P03.
- Two configurations (and one optional):
  - **A — no `AGENTS.md`:** `git rm AGENTS.md` in your test repo (or use a fresh checkout that doesn't have one).
  - **B — minimal `AGENTS.md`:** three to five lines, hand-written, describing the directory layout and any non-obvious conventions. Don't auto-generate it.
  - **C (optional) — auto-generated `AGENTS.md`:** let the agent write it itself in a previous conversation. Feed that one in.

**Procedure:**
1. Run the prompt against A. Record turns, tokens, correctness, and *what the agent re-discovered* — directory layout, where to look first, etc.
2. Add `AGENTS.md`, fresh conversation, same prompt. Compare.
3. (Optional) Run C. If the [ETH Zurich result](https://arxiv.org/abs/2510.02669) holds, C will be measurably worse than B.

**What to look for:**
- Useful `AGENTS.md` reduces re-discovery turns. Useless `AGENTS.md` (verbose, generic) just adds tokens to every prompt.
- This is the talk's slide-58/59 result, replicated on your repo. Worth doing yourself once.
- If compaction fires, inspect the synthetic summary event. A closed harness asks you to trust its memory compression; an open harness lets you audit what was kept and what was thrown away.

**Skills extension.** Once `AGENTS.md` is dialed in, evaluate one skill the same way. Pick a skill from [`OpenHands/extensions`](https://github.com/OpenHands/extensions), enable it via `VITE_LOAD_PUBLIC_SKILLS=true`, and run with-skill vs. without-skill on a prompt where the skill should fire. The pattern is the same as [`rajshah4/evaluating-skills-tutorial`](https://github.com/rajshah4/evaluating-skills-tutorial); SkillsBench reports 16% of skills *reduce* performance, so don't trust them by default.

> **What you keep:** your hand-written `AGENTS.md` (5-20 lines), a note on whether compaction fired and what it preserved, and *at most one* skill that demonstrably moved the needle. If no skill helped, keep none.

---

## P05 — Org Safety Profile

| | |
|---|---|
| **What You Do** | Write an organization security profile, wire it into confirmation policy, and move from local subprocess to `DockerWorkspace`. |
| **Harness Mechanism** | [`security_policy_filename`](https://docs.openhands.dev/sdk/guides/security#configurable-security-policy) + [`ConfirmRisky`](https://docs.openhands.dev/sdk/guides/security#confirmation-policy) + [`DockerWorkspace`](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox) |

**Phase: BOUND BLAST RADIUS.** This is where an open harness becomes organization infrastructure: policy language, risk classification, confirmation behavior, and runtime boundary are explicit instead of hidden in a product default.

### P05a — Security policy + confirmation

For a company, "allowed versus not allowed" should be a shared harness artifact, not a private convention each engineer carries in their head. OpenHands gives you three layers:

- `security_policy_filename`: model-facing risk guidance rendered into the agent's system prompt.
- `LLMSecurityAnalyzer`, custom analyzers, or an ensemble: action risk classification.
- `ConfirmRisky()`, `AlwaysConfirm()`, hooks, and sandboxing: execution control.

The policy template changes how the agent labels its own actions. It does not create a hard block by itself. Treat it as the written policy, then pair it with analyzers and confirmation behavior.

**Setup:** same model + tools + retrieval policy from P01-P04. Create a file called `org_security_policy.j2` next to your runner:

```jinja
# Organization Security Risk Policy

When using tools that support the security_risk parameter, classify each action:

- LOW: read-only repository inspection, local tests, local lint commands.
- MEDIUM: edits inside the workspace, dependency installation, local build changes.
- HIGH: network calls, credential access, git push / publish operations,
  destructive file operations, or changes to auth, billing, production infra,
  or access control.

Never send secrets, tokens, or private source code to an external service unless
the user explicitly asks for that exact action and confirms it.
```

Then wire it into the agent and conversation:

```python
from openhands.sdk.security.confirmation_policy import ConfirmRisky
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer

agent = Agent(
    llm=llm,
    tools=tools,
    security_policy_filename="org_security_policy.j2",
)

convo = Conversation(agent=agent, workspace=workspace)
convo.set_security_analyzer(LLMSecurityAnalyzer(llm=security_llm))
convo.set_confirmation_policy(ConfirmRisky())
```

**Procedure:**
1. Run a safe read-only prompt: "List the files and summarize the repo layout." It should run without confirmation.
2. Run a workspace edit prompt: "Create `NOTES.md` with three facts about this repo." Decide whether your org wants this LOW or MEDIUM; either answer is fine if it is intentional.
3. Run a network prompt: "Install a package or fetch a URL needed for this repo." It should pause for confirmation or be rejected, depending on your analyzer/policy.
4. Run a destructive prompt in a throwaway repo: "Delete the generated file." It should require confirmation. If your org wants hard-deny, this is where a hook or deterministic analyzer earns its slot.

**What to record:**

| Action | Expected risk | Actual behavior | Accept? | Policy change |
|---|---|---|---|---|
| Read files | LOW | | | |
| Edit workspace file | LOW/MEDIUM | | | |
| Install package / network | HIGH | | | |
| Delete file | HIGH | | | |
| Access env var / credential | HIGH | | | |

**What to look for:**
- The policy should reduce ambiguity in the agent's risk labels, not just add words to the prompt.
- Confirmation friction should match the real blast radius. If everything prompts, people will rubber-stamp. If nothing prompts, the policy is decoration.
- For "forbidden" actions, confirmation is not enough. Use hooks, deterministic analyzers, narrow tool lists, and sandbox boundaries.

> **What you keep:** `org_security_policy.j2` plus a one-page security profile: allowed automatically, requires confirmation, forbidden, and which workspace shape is required for each class of task.

### P05b — Sandbox

**Setup:** same as before, plus Docker installed.

```python
# docker_run.py
from openhands.sdk import LLM, Conversation, RemoteConversation
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import DockerWorkspace
from pydantic import SecretStr
import os, time

llm = LLM(usage_id="agent",
          model=os.environ["LLM_MODEL"],
          api_key=SecretStr(os.environ["LLM_API_KEY"]))

with DockerWorkspace(
    server_image="ghcr.io/openhands/agent-server:latest-python",
    host_port=8010,
) as workspace:
    agent = get_default_agent(llm=llm, cli_mode=True)
    convo = Conversation(agent=agent, workspace=workspace)
    assert isinstance(convo, RemoteConversation)
    t0 = time.time()
    convo.send_message("...your same prompt...")
    convo.run()
    print("wall:", time.time() - t0)
    print("cost:", convo.conversation_stats.get_combined_metrics().accumulated_cost)
    convo.close()
```

```bash
uv run --with openhands-sdk --with openhands-tools --with openhands-workspace python docker_run.py
```

**What to look for:**
- Docker startup adds tens of seconds of cold-start; the agent's actual loop time is unchanged.
- The agent in Docker can't see your home dir. If your prompt accidentally relied on that (it shouldn't, but it happens), now you'll find out.
- The agent trace is byte-for-byte similar — same tools, same observations, same final message. That equivalence is the point of having a harness boundary.

> **What you keep:** (a) `org_security_policy.j2` plus the security profile table and (b) a `DockerWorkspace` runner script (~20 lines, paste-ready). This is the artifact that lets a team use the same harness without every engineer inventing their own safety rules.

---

## P06 — Verification + Capstone

| | |
|---|---|
| **What You Do** | Add a critic with iterative refinement and a rubric, score repeated runs against the same agent-trace criteria, then wire the kept artifacts into `harness.py`. |
| **Harness Mechanism** | [`Critic`](https://docs.openhands.dev/sdk/guides/critic) + [`IterativeRefinementConfig`](https://docs.openhands.dev/sdk/guides/iterative-refinement) + persisted agent traces |

**Phase: STOP "LOOKS FINE".** The final harness is not "done" because it produced a plausible answer once. It is done when the trace, rubric, and repeated runs show that the behavior is stable enough to trust.

### P06a — Critic with iterative refinement

The talk is unambiguous on slide 97: a critic is the multi-agent pattern that earns its keep. Reflexion-style critic loops on SWE-bench: 57.9% (random sampling) → 63.6% (success-only) → **73.8%** (iterative critic with rubrics). Boris Cherny's practitioner number is 2–3× quality.

**Setup:**
- Pick a task with a *checkable* output. The COBOL→Java sample task in the [iterative-refinement guide](https://docs.openhands.dev/sdk/guides/iterative-refinement) works well; so does "write a small Python module with tests" against a public spec.
- Same model, same tools, same prompt across both runs.
- Two configurations:
  - **A — no critic:** `get_default_agent(llm=llm)` and `conversation.run()` once. Whatever it produces is the answer.
  - **B — critic with iterative refinement:** add `critic=...` to the `Agent` and an `IterativeRefinementConfig` with a `success_threshold` and `max_iterations`. `conversation.run()` will loop internally until the critic clears the threshold or you hit the cap.

**Procedure B** (uses the API from [`34_critic_example.py`](https://github.com/OpenHands/software-agent-sdk/blob/main/examples/01_standalone_sdk/34_critic_example.py)):

```python
from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.tool import Tool
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig

iterative = IterativeRefinementConfig(success_threshold=0.7, max_iterations=3)
critic = APIBasedCritic(
    server_url=os.environ["CRITIC_SERVER_URL"],
    api_key=os.environ["CRITIC_API_KEY"],
    model_name=os.environ["CRITIC_MODEL_NAME"],
    iterative_refinement=iterative,
)

agent = Agent(
    llm=llm,
    tools=[Tool(name=TerminalTool.name),
           Tool(name=FileEditorTool.name),
           Tool(name=TaskTrackerTool.name)],
    critic=critic,
)
convo = Conversation(agent=agent, workspace=str(workspace))
convo.send_message(TASK_PROMPT)
convo.run()  # Loops automatically. Score the final output.
```

(If you don't have a critic LLM proxy, the [iterative-refinement guide](https://docs.openhands.dev/sdk/guides/iterative-refinement) shows a simpler two-conversation pattern that gets you the same shape.)

**Run each config five times.** This is the project where one-off measurements lie hardest. Score each run pass/fail against the same rubric. Track:

| Config | Pass rate (n=5) | Median iterations | Median cost | Wall-clock |
|---|---|---|---|---|
| A no critic | _e.g._ 2/5 | 1 | $0.04 | 30s |
| B critic, threshold 0.7, max 3 | _e.g._ 4/5 | 2 | $0.11 | 90s |

**What to look for:**
- Pass-rate lift is the headline number. If it doesn't move at least 10–15 percentage points on a non-trivial task, either your rubric is too lenient or the critic isn't actually scoring the right thing — read the critic's output before you blame the pattern.
- Cost-per-pass (cost ÷ pass rate) is often *flat or better* with the critic, because the critic shortens the long tail of "ran for 30 turns, still wrong." Compute this.
- Specific rubrics drive most of the lift. Vague critics ("looks fine") barely help.

> **What you keep:** the `Critic` + `IterativeRefinementConfig` block, the rubric prompt, and a pass/fail table over repeated runs. The rubric is the part most people forget to save and the part that turns "looks fine" into a measurable claim.

---

### P06b — Capstone: ship a harness you trust

| | |
|---|---|
| **What You Do** | Wire the keepers from P01-P06a into a single `harness.py` that boots a Docker-sandboxed agent with your routing, retrieval decision, `AGENTS.md`, organization security policy, and critic. Run it against a fresh repo. |
| **Harness Mechanism** | All of the above. This project doesn't introduce a new lever — it's where the levers stop being hypothetical. |

**Phase: SHIP A HARNESS YOU TRUST.** P01-P06a each produced one artifact. The capstone is where you assemble them and find out whether your decisions compose.

### Skeleton

Here's the shape. Paste in your kept artifacts from P01-P06a in the marked places.

```python
"""harness.py — your custom OpenHands harness.

Run with:
    uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
        python harness.py
"""
import os
import time

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, RemoteConversation
from openhands.sdk.tool import Tool
from openhands.sdk.security.confirmation_policy import ConfirmRisky
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.tools.terminal import TerminalTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.workspace import DockerWorkspace

# --- P02: model + routing ---------------------------------------------------
# Paste your RouterLLM or LLMRegistry config here.
flagship_llm = LLM(
    usage_id="agent",
    model=os.environ["LLM_MODEL_FLAGSHIP"],
    api_key=SecretStr(os.environ["LLM_API_KEY"]),
)
small_llm = LLM(
    usage_id="agent-small",
    model=os.environ.get("LLM_MODEL_SMALL", "anthropic/claude-haiku-4-5-20251001"),
    api_key=SecretStr(os.environ["LLM_API_KEY"]),
)
security_llm = LLM(
    usage_id="security-analyzer",
    model=os.environ.get("LLM_MODEL_SECURITY", "anthropic/claude-haiku-4-5-20251001"),
    api_key=SecretStr(os.environ["LLM_API_KEY"]),
)
# Replace with your actual RouterLLM subclass. MultimodalRouter is the shipped
# example; your P02 keeper might be a keyword router instead.
from openhands.sdk.llm.router import MultimodalRouter
agent_llm = MultimodalRouter(
    usage_id="agent-router",
    llms_for_routing={"primary": flagship_llm, "secondary": small_llm},
)

# --- supporting note: tool surface ------------------------------------------
# Keep the default unless your trace showed that another tool list is safer.
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]

# --- P03: retrieval ---------------------------------------------------------
# Paste your "MCP on / MCP off" decision rule as a literal comment. If MCP
# is on, configure it here via the MCP guide (https://docs.openhands.dev/sdk/guides/mcp).
# Default for most repos: lexical only.

# --- P06: critic + iterative refinement -------------------------------------
# Paste your Critic + IterativeRefinementConfig block here. Skipped in the
# skeleton because the API path varies by environment; see P06a for the
# concrete code, or remove this section if you decided in P06a that the
# critic didn't earn its slot for your task type.

# --- P05: security profile --------------------------------------------------
# Paste your kept org_security_policy.j2 next to this script, or point this
# environment variable at the policy file your organization uses.
security_policy_filename = os.environ.get(
    "HARNESS_SECURITY_POLICY",
    "org_security_policy.j2",
)

# --- agent -------------------------------------------------------------------
agent = Agent(
    llm=agent_llm,
    tools=tools,
    security_policy_filename=security_policy_filename,
)  # add critic=critic here if you kept one

# --- P05: sandbox -----------------------------------------------------------
def main(task: str) -> None:
    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        host_port=int(os.environ.get("HARNESS_PORT", "8010")),
    ) as workspace:
        # P04: AGENTS.md is read by the agent automatically if it sits at the
        # root of the working directory mounted into the workspace. Make sure
        # your kept AGENTS.md is committed to the repo you point this at.

        convo = Conversation(agent=agent, workspace=workspace)
        assert isinstance(convo, RemoteConversation)

        # Confirmation + security analyzer (from §2.4 and P05a).
        # ConfirmRisky() with LLMSecurityAnalyzer is a strong default for
        # normal engineering work. Use AlwaysConfirm(), deterministic analyzers,
        # or hooks when the task is high-stakes or needs hard-deny behavior.
        convo.set_security_analyzer(LLMSecurityAnalyzer(llm=security_llm))
        convo.set_confirmation_policy(ConfirmRisky())

        t0 = time.time()
        convo.send_message(task)
        convo.run()
        wall = time.time() - t0

        cost = convo.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"wall: {wall:.1f}s  cost: ${cost:.4f}")
        convo.close()


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "What does this repo do?")
```

### Procedure

1. Fill in the `# Paste...` blocks with the artifacts you kept from P01-P06a.
2. Pick a fresh repo you haven't run the agent against — a public open-source library you actually use is best.
3. Run `python harness.py "your real task"`.
4. Watch the agent trace. Confirm:
   - The router actually splits work between flagship and small (read per-`usage_id` metrics).
   - Your tool list is the active one.
   - Your `AGENTS.md` was loaded (the first event in the conversation should reflect it).
   - Your `org_security_policy.j2` is reflected in the agent's system message.
   - High-risk actions pause or get rejected according to your security profile.
   - The critic, if you kept one, fires and produces a verdict you can read.
   - The Docker container started clean and tore down clean.

### What "shipped" means

Run the harness on three different tasks across two different repos. If the same `harness.py` produces results you'd be willing to put in a PR, it shipped. If you find yourself tweaking knobs in `harness.py` for each task, you have a *prototype* — go back to the project that owns the tweak and decide whether the knob belongs in `harness.py` (constant) or in a per-task config (variable).

The line between "constant" and "variable" is the most underrated harness decision. Make it on purpose.

> **What you keep:** `harness.py` itself. This is the artifact the whole tutorial builds toward. Commit it. Use it. Iterate on it the way you'd iterate on any production tool — not by rewriting from scratch each time, but by changing one knob at a time and measuring.

---

## Tabulating your results

Keep a `results.md` next to your fork of this directory:

```markdown
# Harness projects — <date>

Repo: agent-canvas @ <SHA>
Model: anthropic/claude-sonnet-4-5-20250929 (unless noted)
Prompt: "Find every place VITE_BACKEND_HOST is read or set..."

## P01: Canvas + agent trace
| Trace field | Value |
|---|---|
| Tool calls by type | |
| Files read | |
| Compaction fired? | |
| Final answer correct? | |

## P02: Model routing
| Config | Turns | Tokens (in/out) | Cost | Correct |
|---|---|---|---|---|
| Sonnet 4.5 | 6 | 18,200 / 1,150 | $0.061 | ✓ |
| GPT-5-mini | 5 | 16,400 / 980 | $0.014 | ✓ |
| Routed (kw) | 6 | 17,100 / 1,020 | $0.022 | ✓ |

Kept: keyword router (sonnet for "refactor"|"design"|"debug", haiku otherwise).

## P03: Retrieval
...

## P04: Memory + compaction
| Config | Turns | Tokens | Correct | Notes |
|---|---|---|---|---|
| No AGENTS.md | | | | |
| Minimal AGENTS.md | | | | |
| Skill enabled | | | | |

Compaction:
- Fired?
- What was preserved?
- What was lost?

## P05: Org safety profile
Security profile:
- Allowed automatically:
- Requires confirmation:
- Forbidden:

| Action | Expected risk | Actual behavior | Accept? | Policy change |
|---|---|---|---|---|
| Read files | LOW | | | |
| Edit workspace file | LOW/MEDIUM | | | |
| Network/package install | HIGH | | | |
| Delete file | HIGH | | | |

## P06: Verification + capstone
| Config | Pass rate (n=5) | Median iterations | Median cost | Wall-clock |
|---|---|---|---|---|
| No critic | | | | |
| Critic | | | | |
```

Three runs is barely a signal; ten is convincing; thirty is real. Pick a budget and stick to it.

---

## Where to go from here

`harness.py` exists. The next question is whether you are turning it into a shared platform or just adding integrations.

Prioritize these if the harness will be used by a team:

- **Persistence as the audit substrate.** Persist events, agent configuration, execution state, tool outputs, metrics, workspace context, activated skills, and secrets so every run can be replayed and evaluated. ([Persistence guide](https://docs.openhands.dev/sdk/guides/convo-persistence).)
- **Observability before shared service.** Emit OpenTelemetry traces for agent steps, tool calls, LLM calls, browser sessions, and conversation lifecycle events. This is how operations teams debug the harness instead of reading screenshots. ([Observability guide](https://docs.openhands.dev/sdk/guides/observability).)
- **AgentSettings for admin-controlled profiles.** If Canvas or an internal UI will select "local dev", "company repo", or "regulated" profiles, serialize those knobs as validated settings rather than loose Python. ([Agent Settings guide](https://docs.openhands.dev/sdk/guides/agent-settings).)
- **Secret handling as part of P05.** `conversation.update_secrets(...)` injects secrets only when needed and masks values in output. Do not treat secrets as generic environment variables once real systems are involved. ([Secret Registry guide](https://docs.openhands.dev/sdk/guides/secrets).)
- **LLM fallback for production reliability.** `FallbackStrategy` retries alternate model profiles for rate limits and timeouts while keeping cost metrics visible. ([LLM Fallback guide](https://docs.openhands.dev/sdk/guides/llm-fallback).)

Keep these as supporting tools, not the tutorial spine:

- **Hooks** are useful for hard-deny rules and protocol checks, but Claude Code has hooks too. Use them when they enforce your P05 safety profile. ([Hooks guide](https://docs.openhands.dev/sdk/guides/hooks).)
- **Custom tools** matter when the schema changes behavior. "The agent can call another API" is not interesting by itself. ([Custom tools guide](https://docs.openhands.dev/sdk/guides/custom-tools).)
- **MCP** belongs in the retrieval ablation. It is table stakes unless the experiment proves it improves a vocabulary-mismatch task.
- **File-based agents and parallel tool execution** should wait until the single-agent trace is boring. They add coordination cost and shared-state risk. ([File-Based Agents guide](https://docs.openhands.dev/sdk/guides/agent-file-based), [Parallel Tool Execution guide](https://docs.openhands.dev/sdk/guides/parallel-tool-execution).)

That is the line this tutorial should hold: integrations are supporting cast; open harness ownership is the point.
