# P05 — Org Safety Profile

| | |
|---|---|
| **What You Do** | Write an organization security profile, wire it into confirmation policy, and move from local subprocess to `DockerWorkspace`. |
| **Harness Mechanism** | [`security_policy_filename`](https://docs.openhands.dev/sdk/guides/security#configurable-security-policy) + [`ConfirmRisky`](https://docs.openhands.dev/sdk/guides/security#confirmation-policy) + [`DockerWorkspace`](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox) |

**Phase: BOUND BLAST RADIUS.** This is where an open harness becomes organization infrastructure: policy language, risk classification, confirmation behavior, and runtime boundary are explicit instead of hidden in a product default.

## Directory guide

| Directory | What's inside |
|---|---|
| `starter/` | `run_safety.py` — runs with local workspace, no security analyzer. Plus `org_security_policy.j2` — a template with TODO placeholders. |
| `solution/` | `run_safety.py` — wires `LLMSecurityAnalyzer` + `ConfirmRisky()` + `DockerWorkspace`. Plus `org_security_policy.j2` — completed policy. |

## P05a — Security policy + confirmation

For a company, "allowed versus not allowed" should be a shared harness artifact, not a private convention each engineer carries in their head. OpenHands gives you three layers:

- `security_policy_filename`: model-facing risk guidance rendered into the agent's system prompt.
- `LLMSecurityAnalyzer`, custom analyzers, or an ensemble: action risk classification.
- `ConfirmRisky()`, `AlwaysConfirm()`, hooks, and sandboxing: execution control.

The policy template changes how the agent labels its own actions. It does not create a hard block by itself. Treat it as the written policy, then pair it with analyzers and confirmation behavior.

### Procedure

1. Fill in the TODOs in `starter/org_security_policy.j2` with your organization's rules.
2. Wire it into `starter/run_safety.py` by completing the TODOs there.
3. Run a safe read-only prompt: "List the files and summarize the repo layout." It should run without confirmation.
4. Run a workspace edit prompt: "Create `NOTES.md` with three facts about this repo." Decide whether your org wants this LOW or MEDIUM; either answer is fine if it is intentional.
5. Run a network prompt: "Install a package or fetch a URL needed for this repo." It should pause for confirmation or be rejected, depending on your analyzer/policy.
6. Run a destructive prompt in a throwaway repo: "Delete the generated file." It should require confirmation. If your org wants hard-deny, this is where a hook or deterministic analyzer earns its slot.

### What to record

| Action | Expected risk | Actual behavior | Accept? | Policy change |
|---|---|---|---|---|
| Read files | LOW | | | |
| Edit workspace file | LOW/MEDIUM | | | |
| Install package / network | HIGH | | | |
| Delete file | HIGH | | | |
| Access env var / credential | HIGH | | | |

### What to look for

- The policy should reduce ambiguity in the agent's risk labels, not just add words to the prompt.
- Confirmation friction should match the real blast radius. If everything prompts, people will rubber-stamp. If nothing prompts, the policy is decoration.
- For "forbidden" actions, confirmation is not enough. Use hooks, deterministic analyzers, narrow tool lists, and sandbox boundaries.

## P05b — Sandbox

Once the policy works, move from local to Docker:

```bash
cd starter  # or solution
uv run --with openhands-sdk --with openhands-tools --with openhands-workspace \
    python run_safety.py --docker
```

### What to look for

- Docker startup adds tens of seconds of cold-start; the agent's actual loop time is unchanged.
- The agent in Docker can't see your home dir. If your prompt accidentally relied on that (it shouldn't, but it happens), now you'll find out.
- The agent trace is byte-for-byte similar — same tools, same observations, same final message. That equivalence is the point of having a harness boundary.

## What you keep

(a) `org_security_policy.j2` plus the security profile table and (b) a `DockerWorkspace` runner script (~20 lines, paste-ready). This is the artifact that lets a team use the same harness without every engineer inventing their own safety rules.

→ Next: [P06 — Verification + Capstone](../p06-capstone/)
