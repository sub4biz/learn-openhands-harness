"""P11 Scenario B: breadth-first research with subagents.

Scenario A showed that subagents lose on a small overlapping repo. A first
attempt at Scenario B used a large code-audit corpus, but live runs showed
that task still did not make subagents look good: the single context found the
same planted issues and cost less. That negative result is part of the lesson.

This version changes the task shape to one that public multi-agent research
systems are built for: independent research branches, compact child findings,
and one synthesis pass.

Generate the corpus first:
    python projects/p11-subagents/make_corpus.py --topics 8 --distractors 8
    python projects/p11-subagents/make_corpus.py --topics 6 --distractors 4 --work-delay 20

Then build the comparison below and run:
    uv run --with openhands-sdk --with openhands-tools \
      python projects/p11-subagents/starter/run_scenario_b.py

Reference:
    uv run --with openhands-sdk --with openhands-tools \
      python projects/p11-subagents/solution/run_scenario_b.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent))   # projects/ for _runtime
sys.path.insert(0, str(PROJECT))          # for subagent_bench

from _runtime import load_dotenv          # noqa: E402

load_dotenv(PROJECT)
import subagent_bench as bench            # noqa: E402,F401


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _topic_windows(report_text: str, topic_id: str, title: str, radius: int = 1800) -> list[str]:
    blob = report_text.lower()
    windows: list[str] = []
    for needle in [topic_id.lower(), title.lower()]:
        if not needle:
            continue
        start = 0
        while True:
            idx = blob.find(needle, start)
            if idx < 0:
                break
            left = max(0, idx - radius)
            right = min(len(blob), idx + len(needle) + radius)
            windows.append(blob[left:right])
            start = idx + len(needle)
    return windows or [blob]


def _fact_aliases(fact: dict) -> set[str]:
    aliases = {str(fact.get("answer", ""))}
    aliases.update(str(alias) for alias in fact.get("aliases", []))
    return {_normalize(alias) for alias in aliases if _normalize(alias)}


def score_facts(report_text: str, ground_truth: dict) -> tuple[int, int]:
    """Count answer facts found near the relevant topic id or title."""
    found = 0
    total = 0
    for topic_id, meta in ground_truth.items():
        title = str(meta.get("title", ""))
        windows = [_normalize(w) for w in _topic_windows(report_text, topic_id, title)]
        for fact in meta.get("facts", []):
            total += 1
            aliases = _fact_aliases(fact)
            if any(any(alias in window for alias in aliases) for window in windows):
                found += 1
    return found, total


def main() -> None:
    load_dotenv(PROJECT)
    if not os.environ.get("LLM_API_KEY"):
        raise SystemExit("Missing LLM_API_KEY")

    corpus = PROJECT / "corpus"
    gt_path = corpus / "ground_truth.json"
    if not gt_path.exists():
        raise SystemExit("Run make_corpus.py first to generate ./corpus.")

    full_ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    topics = sorted(topic_id for topic_id in full_ground_truth if (corpus / topic_id).is_dir())
    limit = os.environ.get("P11_LIMIT_TOPICS")
    if limit:
        topics = topics[: int(limit)]
    ground_truth = {topic_id: full_ground_truth[topic_id] for topic_id in topics}
    print(f"Corpus: {len(topics)} topics, {sum(len(v['facts']) for v in ground_truth.values())} facts\n")

    # TODO (single context): run one conversation across every topic folder.
    # Copy only index.md and topic folders into a temp workspace so the agent
    # cannot read ground_truth.json. Prompt it to produce one row per topic with
    # approved launch window, pilot metric, blocking risk, accountable owner,
    # and short citations. If work_probe.py exists, process topics in order and
    # run `python work_probe.py <topic_id>` once per topic, then include the
    # returned verification code. Score result["final"] with score_facts().
    #
    # TODO (subagents): run one isolated child conversation per topic. Each child
    # should see only its topic folder plus work_probe.py when long-running
    # mode is enabled. Run children concurrently with ThreadPoolExecutor and
    # P11_PARALLELISM. Consider passing
    # bench.resolve_child_model() as model= to child conversations.
    # P11_CHILD_MODEL=same forces children to use LLM_MODEL, which is useful for
    # same-model context-window stress tests.
    #
    # TODO: synthesize the child notes in one final conversation, then print a
    # comparison table with input tokens, output tokens, cost, actual parallel
    # wall time, compaction, and facts found / total.
    raise NotImplementedError(
        "Build the single-context and subagent runs for the research corpus, score facts "
        "against ground_truth.json, and report which config won."
    )


if __name__ == "__main__":
    main()
