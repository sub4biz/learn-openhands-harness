# P07: Verification + Capstone

## What Problem Are You Solving?

A harness is not "done" because it produced a plausible answer once. It is done when the trace, a rubric, and repeated runs show the behavior is stable enough to trust. This is the capstone, in two parts:

1. **Verification.** Add a critic with iterative refinement and a rubric, then score repeated runs against the same criteria. Decide whether the critic earns its cost.
2. **Compose.** Wire every artifact you kept from P01 to P07a into a single `harness.py` and run it on a fresh repo.

Before you run, predict. What pass-rate lift would justify a critic? What cost-per-pass would make it a bad trade? Which P01 to P06 decisions are stable harness constants, and which are per-task variables? What evidence would make you comfortable running the final `harness.py` on a repo you have never touched?

## Start With These Files

Open this README and `starter/` only. Fill the TODOs without reading `solution/`, run the dry run, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| Repeated-run critic experiment | `starter/evaluate.py` (scaffold) | `solution/evaluate.py` (no-critic vs critic, scored) |
| The composed harness | `starter/harness.py` (skeleton with TODOs for every P01 to P06 artifact) | `solution/harness.py` (routing, tools, policy, Docker, optional critic) |

## Part 1: Critic With Iterative Refinement

Critics and iterative refinement are the multi-agent pattern most likely to earn their keep. Reflexion-style critic loops on SWE-bench went 57.9% (random sampling) to 63.6% (success-only) to **73.8%** (iterative critic with rubrics); practitioner reports cite 2 to 3x quality.

Pick a task with a *checkable* output. The solution ships a small `wordstats` task and a deterministic scorer. Hold the model, tools, and prompt constant across two configs:

- **A: no critic.** `get_default_agent(llm=llm)` and one `conversation.run()`. Whatever it produces is the answer.
- **B: critic with iterative refinement.** Add `critic=...` and an `IterativeRefinementConfig`; `run()` loops until the critic clears the threshold or hits the cap.

The critic block used by the evaluator and the capstone:

```python
from openhands.sdk.critic import APIBasedCritic, IterativeRefinementConfig

iterative = IterativeRefinementConfig(success_threshold=0.7, max_iterations=3)
critic = APIBasedCritic(
    server_url=os.environ.get("CRITIC_SERVER_URL", "https://llm-proxy.app.all-hands.dev/vllm"),
    api_key=os.environ.get("CRITIC_API_KEY", os.environ["LLM_API_KEY"]),
    model_name=os.environ.get("CRITIC_MODEL_NAME", "critic"),
    iterative_refinement=iterative,
)
```

`success_threshold=0.7` means "keep refining while the API critic estimates success below 70%." That is separate from the deterministic pass/fail score, which comes from the same rubric for every trial:

```text
Pass only if stats.py exposes analyze_file, cli.py runs, empty files return
zeros, word rules handle hyphens/contractions/numbers, and missing files fail
cleanly.
```

### Run it

Dry-run first:

```bash
cd solution
uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
  python evaluate.py --dry-run --trials 1 --config both
```

Then run each config five times, because this is the project where one-off measurements lie hardest. The command prints the table and writes each scored workspace under `.openhands-runs/p07-evaluate/`:

```bash
uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
  python evaluate.py --trials 5 --config both
```

Score an existing workspace without model calls with `--score-only /path/to/workspace`. If you have no hosted critic endpoint yet, run `--trials 1 --config no-critic` first to verify the Docker workspace, prompt, trace capture, and scorer before wiring `CRITIC_SERVER_URL`, `CRITIC_API_KEY`, and `CRITIC_MODEL_NAME`.

### Record the results

| Config | Pass rate (n=5) | Median iterations | Median cost | Wall-clock |
|---|---|---|---|---|
| A no critic | e.g. 2/5 | 1 | $0.04 | 30s |
| B critic, threshold 0.7, max 3 | e.g. 4/5 | 2 | $0.11 | 90s |

Read it: pass-rate lift is the headline. If it does not move at least 10 to 15 points on a non-trivial task, your rubric is too lenient or the critic is scoring the wrong thing, so read the critic's output before blaming the pattern. Cost-per-pass (cost divided by pass rate) is often flat or better with the critic, because it shortens the long tail of "ran 30 turns, still wrong." Specific rubrics drive most of the lift; "looks fine" critics barely help.

Keep from Part 1: the `Critic` + `IterativeRefinementConfig` block, the rubric prompt, and a pass/fail table over repeated runs.

## Part 2: Capstone, Ship A Harness You Trust

This part introduces no new lever. It is where the levers stop being hypothetical: you wire the keepers from P01 to P07a into one `harness.py` that boots a Docker-sandboxed agent with your routing, retrieval decision, decomposition rule, `AGENTS.md`, org security policy, and critic, then run it on a fresh repo.

1. Open `starter/harness.py` and fill the TODO blocks with your kept artifacts.
2. Pick a fresh repo you have not run the agent against (a public library you actually use is ideal).
3. Run it:

   ```bash
   WORKSPACE_DIR=/path/to/repo \
   uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
     python harness.py "your real task"
   ```

   P07 defaults to Docker host port `8020` (so it does not collide with P06's `8010`); set `HARNESS_PORT` if it is busy. The capstone mounts the policy directory read-only at `/openhands-harness-policy/`; override with `HARNESS_SECURITY_POLICY` if yours lives elsewhere.
4. Watch the trace and confirm: the router sent work to the expected model leg (per-`usage_id` metrics), your tool list is active, your `AGENTS.md` loaded, your `org_security_policy.j2` shows in the system message, high-risk actions paused or were rejected, the critic (if kept) produced a readable verdict, and the Docker container started and tore down clean.

What "shipped" means: run the harness on three tasks across two repos. If the same `harness.py` produces results you would put in a PR, it shipped. If you keep tweaking knobs per task, you have a prototype, so go back to the project that owns the knob and decide whether it is a constant (belongs in `harness.py`) or a variable (per-task config). That constant-versus-variable line is the most underrated harness decision; make it on purpose.

<details>
<summary>References</summary>

- [Critic](https://docs.openhands.dev/sdk/guides/critic) and [IterativeRefinementConfig](https://docs.openhands.dev/sdk/guides/iterative-refinement)
- [Harness engineering talk and slides](https://github.com/rajshah4/harness-engineering#presentation-materials): why critics are the multi-agent pattern most likely to pay off.

</details>

## What Students Should Leave With

`harness.py` itself, the artifact the whole course builds toward. Commit it, use it, and iterate the way you would on any production tool: one knob at a time, measured, not rewritten from scratch.
