"""P11 solution: compare single-context vs. isolated subagent sessions.

Runs the same repo audit two ways on the bundled sample_repo, using the proven
local-SDK RemoteConversation pattern, and prints a token/cost/wall comparison.

Run:
    uv run --with openhands-sdk --with openhands-tools python solution/run_compare.py

Env:
    LLM_API_KEY (required; read from nearest .env if present)
    LLM_MODEL   (default anthropic/claude-sonnet-4-5-20250929)
    P11_CHILD_MODEL or LLM_MODEL_SMALL  optional model for child audits
    P11_CHILD_MODEL=same  force children to use LLM_MODEL
    AGENT_SERVER (default http://127.0.0.1:18000)
    P11_ONLY_DIMS  optional CSV subset of dimensions (e.g. "docs,secrets") for cheap runs
    P11_SINGLE_ONLY=1  run only the single-context config (cheap smoke)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent))   # projects/ for _runtime
sys.path.insert(0, str(PROJECT))          # for subagent_bench

from _runtime import load_dotenv          # noqa: E402

load_dotenv(PROJECT)

import subagent_bench as bench             # noqa: E402


def _load_env() -> None:
    for root in [Path.cwd(), *Path.cwd().parents]:
        env = root / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip().replace("export ", ""), v.strip().strip("\"'"))
            return


def main() -> None:
    _load_env()
    if not os.environ.get("LLM_API_KEY"):
        print("Missing LLM_API_KEY", file=sys.stderr)
        raise SystemExit(2)

    repo_src = PROJECT / "sample_repo"
    dims = bench.DIMENSIONS
    only = os.environ.get("P11_ONLY_DIMS")
    if only:
        wanted = {d.strip() for d in only.split(",")}
        dims = [(k, d) for (k, d) in dims if k in wanted]

    print(f"Auditing: {repo_src}")
    print(f"Dimensions: {[k for k, _ in dims]}\n")
    child_model = bench.resolve_child_model()
    print(f"Child model: {bench.child_model_label(child_model)}\n")

    print("[single context] ...")
    single = bench.run_conversation(
        bench.single_context_prompt(), repo_src, label="single-context")

    if os.environ.get("P11_SINGLE_ONLY") == "1":
        bench.report(single, [], None)
        return

    children = []
    for key, desc in dims:
        print(f"[subagent: {key}] ...")
        r = bench.run_conversation(
            bench._dimension_prompt(key, desc),
            repo_src,
            label=f"subagent:{key}",
            model=child_model,
        )
        children.append(r)

    findings = {r["label"].split(":", 1)[1]: r["final"] for r in children}
    print("[subagent: synthesize] ...")
    synth = bench.run_conversation(
        bench.synthesis_prompt(findings), repo_src, label="subagent:synthesize")

    bench.report(single, children, synth)


if __name__ == "__main__":
    main()
