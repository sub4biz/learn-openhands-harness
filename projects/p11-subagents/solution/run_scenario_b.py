"""P11 solution: Scenario B, breadth-first research with subagents.

Generate a corpus first:
    python projects/p11-subagents/make_corpus.py --topics 8 --distractors 8

Run:
    uv run --with openhands-sdk --with openhands-tools \
      python projects/p11-subagents/solution/run_scenario_b.py

Env:
    LLM_API_KEY (required; read from nearest .env if present)
    LLM_MODEL   (default inherited from subagent_bench)
    P11_CHILD_MODEL or LLM_MODEL_SMALL  optional model for child research
    P11_CHILD_MODEL=same  force children to use LLM_MODEL
    P11_LIMIT_TOPICS optional integer for a cheaper smoke run
    P11_PARALLELISM  optional child concurrency, default 4
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import shutil
import sys
import tempfile
import time
import math
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent))   # projects/ for _runtime
sys.path.insert(0, str(PROJECT))          # for subagent_bench

from _runtime import load_dotenv          # noqa: E402

load_dotenv(PROJECT)

import subagent_bench as bench            # noqa: E402


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _topic_ids(ground_truth: dict) -> list[str]:
    return sorted(ground_truth)


def _topic_title(meta: dict) -> str:
    return str(meta.get("title", ""))


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
        windows = [_normalize(w) for w in _topic_windows(report_text, topic_id, _topic_title(meta))]
        for fact in meta.get("facts", []):
            total += 1
            aliases = _fact_aliases(fact)
            if any(any(alias in window for alias in aliases) for window in windows):
                found += 1
    return found, total


def _topic_list(topics: list[str], ground_truth: dict) -> str:
    return "\n".join(f"- {topic_id}: {_topic_title(ground_truth[topic_id])}" for topic_id in topics)


def _requires_probe(ground_truth: dict) -> bool:
    return any(
        fact.get("label") == "review_code"
        for meta in ground_truth.values()
        for fact in meta.get("facts", [])
    )


def _probe_delay(ground_truth: dict) -> float:
    delays = [float(meta.get("work_delay", 0) or 0) for meta in ground_truth.values()]
    return max(delays, default=0.0)


def _probe_instruction(ground_truth: dict, *, single: bool) -> str:
    if not _requires_probe(ground_truth):
        return ""
    delay = _probe_delay(ground_truth)
    timeout = math.ceil(delay + 15) if delay else 0
    timeout_note = ""
    if delay:
        timeout_note = (
            f"The probe waits about {delay:g} seconds. If your terminal tool "
            f"supports a timeout, set it to at least {timeout} seconds. "
        )
    if single:
        return (
            "This corpus is in long-running mode. For each topic, run "
            "`python work_probe.py <topic_id>` from the corpus root and include "
            f"the returned verification code. {timeout_note}In this single-context baseline, "
            "process the listed topics in order, one probe at a time, so the "
            "trace measures one sequential conversation.\n\n"
        )
    return (
        "This corpus is in long-running mode. Run "
        "`python work_probe.py <topic_id>` from the corpus root for your topic "
        f"and include the returned verification code. {timeout_note}\n\n"
    )


def _single_prompt(topics: list[str], ground_truth: dict) -> str:
    return (
        "You are doing a breadth-first research synthesis across local topic "
        "folders. For every topic listed below, read its packet.md and "
        "questions.md. Use only current packet evidence. Superseded notes and "
        "appendices are distractors. Return one row per topic with topic id, "
        "project name, approved launch window, pilot metric, blocking risk, "
        "accountable owner, any verification code required by the questions, "
        "and short source citations. Do not modify files.\n\n"
        f"{_probe_instruction(ground_truth, single=True)}"
        f"{_topic_list(topics, ground_truth)}"
    )


def _child_prompt(topic_id: str, meta: dict) -> str:
    return (
        f"Research ONLY {topic_id}: {_topic_title(meta)}. Read packet.md and "
        "questions.md in that topic folder. Use only current packet evidence. "
        "Superseded notes and appendices are distractors. Return the topic id, "
        "project name, approved launch window, pilot metric, blocking risk, "
        "accountable owner, any verification code required by the questions, "
        "and short source citations. "
        f"{_probe_instruction({topic_id: meta}, single=False)}"
        "Do not inspect other "
        "topics and do not modify files."
    )


def _synthesis_prompt(findings: dict[str, str]) -> str:
    body = "\n\n".join(f"## {topic_id}\n{text}" for topic_id, text in findings.items())
    return (
        "Combine these independent topic research notes into one concise table. "
        "Preserve every topic id and project name. Preserve each approved "
        "launch window, pilot metric, blocking risk, accountable owner, and "
        "verification code exactly when available. Preserve source citations. "
        "Do not invent facts beyond the child notes. Return the table as your "
        "final answer. Do not read the repo and do not create, edit, or delete "
        "files.\n\n"
        f"{body}"
    )


def _copy_topics(src: Path, dst: Path, topics: list[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    index = src / "index.md"
    if index.exists():
        shutil.copy2(index, dst / "index.md")
    probe = src / "work_probe.py"
    if probe.exists():
        shutil.copy2(probe, dst / "work_probe.py")
    for topic_id in topics:
        shutil.copytree(src / topic_id, dst / topic_id)


def _sum(rows: list[dict], key: str) -> float:
    return sum(float(row.get(key, 0) or 0) for row in rows)


def _print_row(label: str, tokens_in: float, tokens_out: float, cost: float,
               wall: float, compactions: float, score: tuple[int, int]) -> None:
    found, total = score
    compact = "yes" if compactions else "no"
    print(
        f"| {label:<22} | {tokens_in:>10,.0f} | {tokens_out:>10,.0f} | "
        f"${cost:>8.4f} | {wall:>7.1f}s | {compact:^10} | {found:>3}/{total:<3} |"
    )


def _run_children(
    corpus: Path,
    scratch: Path,
    topics: list[str],
    ground_truth: dict,
    child_model: str | None,
    parallelism: int,
) -> tuple[list[dict], float]:
    def run_one(topic_id: str) -> dict:
        child_src = scratch / f"child_{topic_id}"
        _copy_topics(corpus, child_src, [topic_id])
        row = bench.run_conversation(
            _child_prompt(topic_id, ground_truth[topic_id]),
            child_src,
            label=f"scenario-b:{topic_id}",
            model=child_model,
        )
        row["topic_id"] = topic_id
        return row

    t0 = time.time()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        future_to_topic = {executor.submit(run_one, topic_id): topic_id for topic_id in topics}
        for future in as_completed(future_to_topic):
            topic_id = future_to_topic[future]
            row = future.result()
            rows.append(row)
            score = score_facts(row["final"], {topic_id: ground_truth[topic_id]})
            print(
                f"[subagent] child complete: {topic_id} "
                f"facts={score[0]}/{score[1]} cost=${row['cost']:.4f} wall={row['wall']:.1f}s"
            )
    elapsed = time.time() - t0
    rows.sort(key=lambda row: row["topic_id"])
    return rows, elapsed


def report(
    single: dict,
    children: list[dict],
    child_elapsed: float,
    synth: dict,
    ground_truth: dict,
    parallelism: int,
) -> None:
    child_text = "\n\n".join(row["final"] for row in children)
    sub_rows = [*children, synth]
    single_score = score_facts(single["final"], ground_truth)
    child_score = score_facts(child_text, ground_truth)
    synth_score = score_facts(synth["final"], ground_truth)
    sub_wall = child_elapsed + synth["wall"]

    print("\n" + "=" * 98)
    print("P11 Scenario B: breadth-first research")
    print("=" * 98)
    print(f"Parallel child limit: {parallelism}")
    print(
        "| Config                 |  Input tok | Output tok |     Cost |    Wall | Compacted? | Facts |"
    )
    print("|---|---:|---:|---:|---:|:---:|---:|")
    _print_row(
        "single context",
        single["in"],
        single["out"],
        single["cost"],
        single["wall"],
        single.get("compactions", 0),
        single_score,
    )
    _print_row(
        "subagents+synth",
        _sum(sub_rows, "in"),
        _sum(sub_rows, "out"),
        _sum(sub_rows, "cost"),
        sub_wall,
        _sum(sub_rows, "compactions"),
        synth_score,
    )

    print(f"\nRaw child fact completeness before synthesis: {child_score[0]}/{child_score[1]}")
    print(f"Child elapsed wall time: {child_elapsed:.1f}s")
    if single["cost"]:
        print(f"Cost ratio (subagents / single): {_sum(sub_rows, 'cost') / single['cost']:.2f}x")
    if single["wall"]:
        print(f"Wall ratio (subagents / single): {sub_wall / single['wall']:.2f}x")

    if synth_score[0] > single_score[0]:
        print("Winner: subagents, because isolated topic researchers found more facts.")
    elif synth_score[0] == single_score[0] and sub_wall < single["wall"]:
        print("Winner: subagents, because completeness tied and parallel wall time was lower.")
    elif synth_score[0] == single_score[0]:
        print("Result: completeness tied. Compare wall time, cost, and compaction before deciding.")
    else:
        print("Winner: single context on this corpus size. Increase breadth before claiming value.")
    print("=" * 98)


def main() -> None:
    load_dotenv(PROJECT)
    if not os.environ.get("LLM_API_KEY"):
        raise SystemExit("Missing LLM_API_KEY")

    corpus = PROJECT / "corpus"
    gt_path = corpus / "ground_truth.json"
    if not gt_path.exists():
        raise SystemExit("Run make_corpus.py first to generate projects/p11-subagents/corpus.")

    full_ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    topics = [topic_id for topic_id in _topic_ids(full_ground_truth) if (corpus / topic_id).is_dir()]
    limit = os.environ.get("P11_LIMIT_TOPICS")
    if limit:
        topics = topics[: int(limit)]
    ground_truth = {topic_id: full_ground_truth[topic_id] for topic_id in topics}
    if not topics:
        raise SystemExit("No topic_* folders found in corpus.")

    child_model = bench.resolve_child_model()
    parallelism = int(os.environ.get("P11_PARALLELISM", "4"))
    if parallelism < 1:
        raise SystemExit("P11_PARALLELISM must be at least 1.")

    print(f"Corpus: {len(topics)} topics")
    print(f"Subagent children: {len(topics)} topic researchers")
    print(f"Parallel child limit: {parallelism}")
    print(f"Child model: {bench.child_model_label(child_model)}")
    if _requires_probe(ground_truth):
        print("Long-running mode: work_probe.py required")

    with tempfile.TemporaryDirectory(prefix="p11_scenario_b_") as scratch_raw:
        scratch = Path(scratch_raw)
        single_src = scratch / "single"
        _copy_topics(corpus, single_src, topics)

        print("\n[single context] research ...")
        single = bench.run_conversation(
            _single_prompt(topics, ground_truth),
            single_src,
            label="scenario-b:single",
        )

        print("\n[subagents] child topic researchers ...")
        children, child_elapsed = _run_children(
            corpus,
            scratch,
            topics,
            ground_truth,
            child_model,
            parallelism,
        )

        findings = {row["topic_id"]: row["final"] for row in children}
        synth_src = scratch / "synthesis"
        synth_src.mkdir()
        print("[subagents] synthesize child findings ...")
        synth = bench.run_conversation(
            _synthesis_prompt(findings),
            synth_src,
            label="scenario-b:synthesize",
        )

    report(single, children, child_elapsed, synth, ground_truth, parallelism)


if __name__ == "__main__":
    main()
