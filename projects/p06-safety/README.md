# P06: Org Safety Profile

## What Problem Are You Solving?

For a company, "allowed versus not allowed" should be a shared harness artifact, not a private convention each engineer carries in their head. This is where an open harness becomes organization infrastructure: the policy language, risk classification, confirmation behavior, and runtime boundary are explicit instead of hidden in a product default.

You do this in two parts:

1. **Policy and confirmation.** Write an org security policy, classify actions by risk, and pause on the risky ones.
2. **Sandbox.** Move the same run from a local subprocess into `DockerWorkspace` and confirm the trace is unchanged.

Before you run, predict. Which actions are LOW, MEDIUM, and HIGH for your org? Which prompts should run without confirmation, and which should pause? What should happen to package installs, network access, deletes, and secrets? What changes when the same prompt runs inside Docker?

## Start With These Files

Open this README and `starter/` only. Fill the TODOs without reading `solution/`, dry-classify, run the prompts, then compare against `solution/` and read `solution/README.md` for the brief.

| Purpose | Starter | Solution |
|---|---|---|
| The policy | `starter/org_security_policy.j2` (TODO placeholders) | `solution/org_security_policy.j2` (completed) |
| Run + classify + confirm + sandbox | `starter/run_safety.py` (local, no analyzer) | `solution/run_safety.py` (analyzers + `ConfirmRisky` + `DockerWorkspace`, `--classify-dry`, terminal confirmation) |

## Part 1: Security Policy + Confirmation

OpenHands gives you three layers, and the policy file alone is not a hard block:

- `security_policy_filename`: model-facing risk guidance rendered into the system prompt. It changes how the agent labels its own actions.
- Analyzers (deterministic, LLM-assessed, or an ensemble): action risk classification.
- `ConfirmRisky()`, `AlwaysConfirm()`, hooks, sandboxing: execution control.

The solution's `EnsembleSecurityAnalyzer` wraps three sub-analyzers, each catching what the others miss, and returns the maximum severity (a child crash counts as HIGH, so a failure is loud, not a silent pass):

- **`PolicyRailSecurityAnalyzer`**: named structural rules (fetch-to-exec, raw-disk-op, catastrophic-delete) checked per normalized segment, so a dangerous mention in the agent's *reasoning* does not trip a rail meant for what gets *executed*.
- **`PatternSecurityAnalyzer`**: signature scans, with tool args checked for shell-destructive and code-execution patterns and all fields checked for prompt injection. Different threats live in different fields.
- **`LLMSecurityAnalyzer`**: reads the `security_risk` the generating model already attached (no second model call), catching semantic intent no pattern library can enumerate.

The deterministic analyzers overlap on obvious cases (`rm -rf /`, `curl ... | sh`); that redundancy is the point. They diverge on prompt injection (Pattern only), cross-field safety (PolicyRail only), and novel intent (LLM only).

### Run it

Fill the TODOs in `starter/org_security_policy.j2` and wire it into `starter/run_safety.py`. Before any model call, sanity-check representative actions:

```bash
cd solution
uv run --with openhands-sdk --with openhands-tools python run_safety.py --classify-dry
```

The solution classifies package installs and file deletion as HIGH, so `ConfirmRisky(threshold=MEDIUM)` pauses on them. Then run prompts of escalating risk: a read-only summary (should not pause), a workspace edit (LOW or MEDIUM, your call), a network/install prompt, and a delete in a throwaway repo (should pause). The runner rejects pending actions by default so terminal runs do not hang; add `--interactive` to approve or reject yourself:

```bash
uv run --with openhands-sdk --with openhands-tools python run_safety.py network
uv run --with openhands-sdk --with openhands-tools python run_safety.py --interactive network
```

### Record the results

| Action | Expected risk | Dry analyzer risk | Actual behavior | Accept? | Policy change |
|---|---|---|---|---|---|
| Read files | LOW | | | | |
| Edit workspace file | LOW/MEDIUM | | | | |
| Install package / network | HIGH | | | | |
| Delete file | HIGH | | | | |
| Access env var / credential | HIGH | | | | |

Read it: the policy should reduce ambiguity in the agent's risk labels, not just add words. Confirmation friction should match real blast radius. If everything prompts, people rubber-stamp; if nothing prompts, the policy is decoration. For truly forbidden actions, confirmation is not enough; use hooks, deterministic analyzers, narrow tool lists, and the sandbox.

## Part 2: Sandbox With DockerWorkspace

Once the policy works, move from local to Docker:

```bash
cd solution
WORKSPACE_DIR=/path/to/repo \
uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
    python run_safety.py --docker
```

The solution mounts `WORKSPACE_DIR` into the sandbox and the policy template read-only at `/openhands-harness-policy/`, and preflights `docker info` so a missing daemon gives a short error instead of a deep stack trace.

Read it: Docker adds tens of seconds of cold start, but the agent's loop time is unchanged. The agent can no longer see your home directory, so any prompt that secretly relied on it will now fail loudly. The trace is otherwise byte-for-byte similar, with the same tools, observations, and final message. That equivalence is the whole point of a harness boundary.

<details>
<summary>References</summary>

- [Configurable security policy](https://docs.openhands.dev/sdk/guides/security#configurable-security-policy)
- [Confirmation policy](https://docs.openhands.dev/sdk/guides/security#confirmation-policy)
- [DockerWorkspace sandbox](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)

</details>

## What Students Should Leave With

(a) `org_security_policy.j2` plus the security profile table, and (b) the runner patterns you reuse: dry classification, terminal confirmation handling, and `DockerWorkspace` preflight. This is what lets a team share one harness instead of every engineer inventing their own safety rules.

Next: [P07: Verification + Capstone](../p07-capstone/)
