"""
Shared scaffolding for P11: single context vs. isolated subagent sessions.

Both configs run the SAME audit on the SAME repo, using the proven local-SDK
RemoteConversation pattern from P01-P08 (LLM_API_KEY from .env, local agent
server). The only difference is the context boundary:

  - single  : one conversation audits all dimensions in one growing context.
  - subagents: one isolated conversation per dimension (a fresh context each),
               plus a synthesis conversation that never touches the repo.

We measure input tokens, output tokens, cost, and wall time for each, so the
"does isolation actually save tokens / improve quality" question is answered
with numbers, not assertion.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parents[1]
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

from pydantic import SecretStr
from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace
from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.tools.preset.default import get_default_agent
from _runtime import resolve_api_key, server_visible_path, token_counts

_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store")


def _copy_repo(src: Path) -> Path:
    """Copy the audit target to a throwaway temp dir so runs never mutate the
    bundled repo and each conversation starts from a clean tree."""
    dst = Path(tempfile.mkdtemp(prefix="p11_audit_")) / "repo"
    shutil.copytree(src, dst, ignore=_IGNORE)
    return dst

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"
DEFAULT_SERVER = "http://127.0.0.1:18000"
SAME_MODEL_SENTINELS = {"same", "main", "none"}

# Five independent audit dimensions. Each is a scoped subtask whose result is
# small (a few sentences) even though finding it reads files and reasons.
DIMENSIONS = [
    ("docs", "documentation accuracy: does README.md match what the code and CLI actually do?"),
    ("errors", "error handling: bare excepts, swallowed exceptions, silent failures"),
    ("secrets", "secret handling: hardcoded credentials, API keys, or tokens"),
    ("deps", "dependency hygiene: unpinned versions and declared-but-unused dependencies"),
    ("tests", "tests: do the documented test command and any test files actually exist and run?"),
]

FINDING_CONTRACT = (
    "Report only concrete findings with file and line evidence, in 2-4 sentences. "
    "Do not modify any files."
)


def resolve_child_model() -> str | None:
    raw = os.environ.get("P11_CHILD_MODEL")
    if raw:
        value = raw.strip()
        if value.lower() in SAME_MODEL_SENTINELS:
            return None
        return value
    return os.environ.get("LLM_MODEL_SMALL")


def child_model_label(child_model: str | None) -> str:
    raw = os.environ.get("P11_CHILD_MODEL")
    if raw and raw.strip().lower() in SAME_MODEL_SENTINELS:
        return "same as LLM_MODEL"
    if child_model:
        return child_model
    return "same as LLM_MODEL"


def _dimension_prompt(key: str, desc: str) -> str:
    return (
        f"Audit ONLY this one dimension of the repository in your workspace: {desc}\n\n"
        f"{FINDING_CONTRACT} Audit nothing else."
    )


def single_context_prompt() -> str:
    lines = "\n".join(f"  {i+1}. {desc}" for i, (_, desc) in enumerate(DIMENSIONS))
    return (
        "Audit the repository in your workspace across all of these dimensions:\n"
        f"{lines}\n\n"
        f"{FINDING_CONTRACT} Produce one findings report covering every dimension."
    )


def synthesis_prompt(findings: dict[str, str]) -> str:
    body = "\n\n".join(f"## {k}\n{v}" for k, v in findings.items())
    return (
        "Combine these independent audit findings into one short report, grouped "
        "by dimension. Do not invent findings beyond what is given. Return the "
        "report as your final answer. Do not read the repo and do not create, "
        "edit, or delete files.\n\n" + body
    )


def _final_text(conversation: RemoteConversation) -> str:
    """Last agent response, whether returned as text or through finish."""
    return get_agent_final_response(conversation.state.events).strip()


def _count_compactions(conversation: RemoteConversation) -> int:
    count = 0
    for event in conversation.state.events:
        event_type = (getattr(event, "type", None) or type(event).__name__).lower()
        if "compact" in event_type or "condens" in event_type:
            count += 1
    return count


def run_conversation(prompt: str, repo_src: str | Path, *, label: str,
                     server: str = DEFAULT_SERVER, model: str | None = None) -> dict:
    """Run one isolated conversation against a fresh copy of repo_src and return
    its metrics + final text. Each call gets its own clean workspace.

    Pass `model` to override LLM_MODEL for this conversation (e.g. route a heavy
    reading subagent to a cheaper model than the synthesis step)."""
    api_key = os.environ["LLM_API_KEY"]
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    working_dir = server_visible_path(_copy_repo(Path(repo_src)))
    llm = LLM(usage_id="agent", model=model, api_key=SecretStr(api_key))
    agent = get_default_agent(llm=llm, cli_mode=True)
    workspace = Workspace(host=server, api_key=resolve_api_key(), working_dir=working_dir)
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)
    try:
        t0 = time.time()
        conversation.send_message(prompt)
        conversation.run()
        wall = time.time() - t0
        m = conversation.conversation_stats.get_combined_metrics()
        pin, pout = token_counts(m)
        return {
            "label": label,
            "in": pin,
            "out": pout,
            "cost": float(getattr(m, "accumulated_cost", 0.0) or 0.0),
            "wall": wall,
            "events": len(conversation.state.events),
            "compactions": _count_compactions(conversation),
            "final": _final_text(conversation),
        }
    finally:
        conversation.close()


def fmt_row(r: dict) -> str:
    return (f"  {r['label']:<24} in={r['in']:>8,} out={r['out']:>6,} "
            f"cost=${r['cost']:>7.4f} wall={r['wall']:>5.1f}s "
            f"events={r['events']:>3} comp={r.get('compactions', 0):>2}")


def report(single: dict, children: list[dict], synth: dict | None) -> None:
    print("\n" + "=" * 72)
    print("P11: single context vs. isolated subagent sessions")
    print("=" * 72)
    print("\n[single context]")
    print(fmt_row(single))
    if not children and synth is None:
        print("=" * 72)
        return
    print("\n[subagents] (one isolated session per dimension)")
    for r in children:
        print(fmt_row(r))
    if synth:
        print(fmt_row(synth))
    c_in = sum(r["in"] for r in children) + (synth["in"] if synth else 0)
    c_out = sum(r["out"] for r in children) + (synth["out"] if synth else 0)
    c_cost = sum(r["cost"] for r in children) + (synth["cost"] if synth else 0)
    c_wall = sum(r["wall"] for r in children) + (synth["wall"] if synth else 0)
    print("\n" + "-" * 72)
    print(f"  {'TOTAL single':<24} in={single['in']:>8,} out={single['out']:>6,} "
          f"cost=${single['cost']:>7.4f} wall={single['wall']:>5.1f}s")
    print(f"  {'TOTAL subagents':<24} in={c_in:>8,} out={c_out:>6,} "
          f"cost=${c_cost:>7.4f} wall={c_wall:>5.1f}s")
    if single["cost"]:
        print(f"\n  cost ratio (subagents / single): {c_cost / single['cost']:.2f}x")
    print("=" * 72)
