"""P11 starter: compare single-context vs. isolated subagent sessions.

The single-context run is given. Your job is the subagent run: the same audit
as one isolated conversation per dimension, then a synthesis conversation that
combines the findings. Measure both and decide whether isolation paid off.

Run:
    uv run --with openhands-sdk --with openhands-tools python starter/run_compare.py

Env:
    LLM_API_KEY (required; read from nearest .env if present)
    P11_CHILD_MODEL or LLM_MODEL_SMALL  optional model for child audits
    P11_CHILD_MODEL=same  force children to use LLM_MODEL
    AGENT_SERVER (default http://127.0.0.1:18000)
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

    # Single context (given).
    print("[single context] ...")
    single = bench.run_conversation(
        bench.single_context_prompt(), repo_src, label="single-context")

    if os.environ.get("P11_SINGLE_ONLY") == "1":
        bench.report(single, [], None)
        return

    # Subagents: isolated sessions, one per dimension (your work).
    # Run one conversation per dimension in bench.DIMENSIONS, each scoped to a
    # single dimension via bench._dimension_prompt(key, desc). Collect the final
    # text of each, then run one more conversation with bench.synthesis_prompt(
    # findings) to combine them. Build a `children` list and a `synth` dict the
    # same shape bench.run_conversation returns, then call bench.report(...).
    # Use bench.resolve_child_model() as the optional model= value for child
    # audits. P11_CHILD_MODEL=same forces children to use LLM_MODEL, which is
    # useful for same-model context-window stress tests.
    #
    # child_model = bench.resolve_child_model()
    # children = []
    # for key, desc in bench.DIMENSIONS:
    #     children.append(bench.run_conversation(
    #         bench._dimension_prompt(key, desc),
    #         repo_src,
    #         label=f"subagent:{key}",
    #         model=child_model,
    #     ))
    # findings = {r["label"].split(":", 1)[1]: r["final"] for r in children}
    # synth = bench.run_conversation(
    #     bench.synthesis_prompt(findings), repo_src, label="subagent:synthesize")
    # bench.report(single, children, synth)
    raise NotImplementedError("Implement the subagent run, then call bench.report(single, children, synth).")


if __name__ == "__main__":
    main()
