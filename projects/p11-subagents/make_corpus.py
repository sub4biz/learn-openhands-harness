"""Generate the Scenario B research corpus.

Scenario B is a breadth-first research task. The corpus contains independent
topic packets. Each packet has current evidence, superseded notes, and
distractors. The benchmark asks one conversation to research every topic, then
compares that with isolated child conversations that each handle one topic.

Usage:
    python projects/p11-subagents/make_corpus.py
    python projects/p11-subagents/make_corpus.py --topics 8 --distractors 8
    python projects/p11-subagents/make_corpus.py --topics 6 --work-delay 20
    python projects/p11-subagents/make_corpus.py --out corpus
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PROJECTS = [
    ("Northstar Atlas", "hospital discharge planning"),
    ("Cedar Signal", "utility outage triage"),
    ("Harbor Relay", "port appointment scheduling"),
    ("Quartz Loom", "claims intake review"),
    ("Juniper Gate", "campus access support"),
    ("Violet Ledger", "grant reimbursement tracking"),
    ("Summit Lens", "field inspection routing"),
    ("Prairie Trace", "cold-chain exception handling"),
    ("Copper Beacon", "warehouse replenishment"),
    ("Silver Finch", "loan document preparation"),
    ("Maple Anchor", "resident services intake"),
    ("Orchid Span", "care team handoffs"),
]

OWNERS = [
    "Mira Patel",
    "Jonah Reed",
    "Leah Okafor",
    "Samir Chen",
    "Nadia Brooks",
    "Evan Ross",
    "Priya Menon",
    "Mateo Alvarez",
    "Iris Wong",
    "Noah Singh",
    "Elena Garcia",
    "Ari Klein",
]

RISKS = [
    "data residency review",
    "union scheduling approval",
    "vendor rate-limit waiver",
    "identity proofing backlog",
    "accessibility regression review",
    "duplicate vendor records",
    "field tablet certificate rotation",
    "temperature sensor calibration",
    "supplier EDI mapping",
    "manual signature exception",
    "language access validation",
    "weekend coverage gap",
]

METRIC_NOUNS = [
    "lower escalation rate",
    "shorter manual review time",
    "fewer duplicate tickets",
    "higher first-pass completion",
    "lower missed appointment rate",
    "faster supervisor review",
    "higher document match rate",
    "lower exception backlog",
]

WINDOWS = [
    ("2026 Q3", ["Q3 2026", "third quarter of 2026"]),
    ("2026 Q4", ["Q4 2026", "fourth quarter of 2026"]),
    ("2027 Q1", ["Q1 2027", "first quarter of 2027"]),
    ("2027 Q2", ["Q2 2027", "second quarter of 2027"]),
    ("2027 Q3", ["Q3 2027", "third quarter of 2027"]),
    ("2027 Q4", ["Q4 2027", "fourth quarter of 2027"]),
]


def _pct(idx: int) -> int:
    return 11 + ((idx * 7) % 23)


def _review_code(idx: int, title: str) -> str:
    initials = "".join(part[0] for part in title.split()).upper()
    return f"RV-{idx:03d}-{initials}-{(idx * 37 + 113) % 997:03d}"


def _topic(idx: int, distractors: int, work_delay: float) -> dict:
    title, domain = PROJECTS[idx % len(PROJECTS)]
    owner = OWNERS[idx % len(OWNERS)]
    risk = RISKS[idx % len(RISKS)]
    window, window_aliases = WINDOWS[idx % len(WINDOWS)]
    metric = f"{_pct(idx)} percent {METRIC_NOUNS[idx % len(METRIC_NOUNS)]}"
    metric_aliases = [
        metric,
        metric.replace(" percent ", "% "),
        f"{_pct(idx)} percent improvement in {METRIC_NOUNS[idx % len(METRIC_NOUNS)]}",
    ]
    topic_id = f"topic_{idx:03d}"
    facts = [
        {
            "label": "approved_window",
            "question": "What is the approved launch window?",
            "answer": window,
            "aliases": [window, *window_aliases],
        },
        {
            "label": "pilot_metric",
            "question": "What measured pilot outcome should leadership cite?",
            "answer": metric,
            "aliases": metric_aliases,
        },
        {
            "label": "blocking_risk",
            "question": "What is the main blocking risk?",
            "answer": risk,
            "aliases": [risk],
        },
        {
            "label": "accountable_owner",
            "question": "Who is the accountable owner?",
            "answer": owner,
            "aliases": [owner],
        },
    ]
    if work_delay > 0:
        code = _review_code(idx, title)
        facts.append(
            {
                "label": "review_code",
                "question": "What verification code did work_probe.py return?",
                "answer": code,
                "aliases": [code],
            }
        )
    return {
        "id": topic_id,
        "title": title,
        "domain": domain,
        "distractors": distractors,
        "work_delay": work_delay,
        "review_code": _review_code(idx, title) if work_delay > 0 else "",
        "facts": facts,
    }


def _decoy_window(idx: int) -> str:
    return WINDOWS[(idx + 2) % len(WINDOWS)][0]


def _decoy_owner(idx: int) -> str:
    return OWNERS[(idx + 3) % len(OWNERS)]


def _decoy_metric(idx: int) -> str:
    return f"{5 + ((idx * 5) % 19)} percent {METRIC_NOUNS[(idx + 4) % len(METRIC_NOUNS)]}"


def _fact(topic: dict, label: str) -> str:
    for fact in topic["facts"]:
        if fact["label"] == label:
            return str(fact["answer"])
    raise KeyError(label)


def _distractor_sections(topic: dict) -> str:
    topic_idx = int(topic["id"].split("_")[1])
    sections = []
    for n in range(topic["distractors"]):
        sections.append(
            "\n".join(
                [
                    f"## Appendix {n + 1}: Unrelated Tracking Note",
                    "Status: background reference only.",
                    (
                        f"The adjacent workstream logged {_decoy_metric(topic_idx + n)} "
                        f"and floated {_decoy_window(topic_idx + n)} as a planning date. "
                        f"{_decoy_owner(topic_idx + n)} owns that adjacent workstream, "
                        "not the topic in this packet."
                    ),
                    (
                        "Use this appendix to understand nearby operational noise. "
                        "Do not treat it as the current decision record."
                    ),
                ]
            )
        )
    return "\n\n".join(sections)


def _packet(topic: dict) -> str:
    topic_idx = int(topic["id"].split("_")[1])
    parts = [
        f"# {topic['id']}: {topic['title']}",
        f"Domain: {topic['domain']}.",
        (
            "Research instruction: answer only from current packet evidence. "
            "Some notes are explicitly superseded and are included to test "
            "whether the researcher can separate current evidence from stale "
            "planning noise."
        ),
    ]
    if topic["work_delay"] > 0:
        parts.append(
            "Long-running review instruction: after reading this packet, run "
            f"`python work_probe.py {topic['id']}` from the corpus root and "
            "include the returned verification code in your final answer."
        )
    parts.extend(
        [
            "## Source A: Superseded Kickoff Note",
            "Status: superseded by Source B.",
            (
                f"The kickoff draft proposed {_decoy_window(topic_idx)} and named "
                f"{_decoy_owner(topic_idx)} as temporary owner. It also claimed "
                f"{_decoy_metric(topic_idx)} from a small internal rehearsal. "
                "The steering group later rejected these values."
            ),
            "## Source B: Current Steering Decision",
            "Status: current.",
            (
                f"The approved launch window for {topic['title']} is "
                f"{_fact(topic, 'approved_window')}. The accountable owner is "
                f"{_fact(topic, 'accountable_owner')}. The main blocking risk is "
                f"{_fact(topic, 'blocking_risk')}."
            ),
            "## Source C: Pilot Measurement",
            "Status: current.",
            (
                f"The pilot result leadership should cite is "
                f"{_fact(topic, 'pilot_metric')}. The measurement came from the "
                "current pilot review, not from the superseded kickoff note."
            ),
            "## Source D: Reviewer's Caution",
            "Status: current.",
            (
                "The final answer should include the topic id, the project name, "
                "the approved window, the pilot metric, the blocking risk, and the "
                "accountable owner. Cite Source B for window, owner, and risk. "
                "Cite Source C for the pilot metric."
            ),
            _distractor_sections(topic),
        ]
    )
    return "\n\n".join(parts) + "\n"


def _questions(topic: dict) -> str:
    lines = [
        f"# {topic['id']}: {topic['title']}",
        "Answer these questions from packet.md:",
    ]
    for fact in topic["facts"]:
        lines.append(f"- {fact['question']}")
    return "\n".join(lines) + "\n"


def _index(topics: list[dict]) -> str:
    lines = [
        "# Research Corpus Index",
        "",
        "Each topic folder contains packet.md and questions.md. The benchmark",
        "asks agents to answer every topic from packet evidence only.",
        "",
    ]
    if topics and topics[0]["work_delay"] > 0:
        lines.extend(
            [
                f"Long-running mode: run `python work_probe.py <topic_id>` for each topic.",
                "The single-context baseline processes probes in topic order.",
                "",
            ]
        )
    for topic in topics:
        lines.append(f"- {topic['id']}: {topic['title']} ({topic['domain']})")
    return "\n".join(lines) + "\n"


def _work_probe_source(topics: list[dict], delay: float) -> str:
    work = {
        topic["id"]: {
            "topic_id": topic["id"],
            "project": topic["title"],
            "verification_code": topic["review_code"],
            "review_status": "complete",
        }
        for topic in topics
    }
    return (
        '"""Slow local review probe for P11 Scenario B long-running mode."""\n'
        "from __future__ import annotations\n\n"
        "import argparse\n"
        "import json\n"
        "import time\n\n"
        f"DELAY_SECONDS = {delay!r}\n"
        f"WORK = {work!r}\n\n"
        "def main() -> None:\n"
        "    parser = argparse.ArgumentParser(description=__doc__)\n"
        "    parser.add_argument('topic_id')\n"
        "    args = parser.parse_args()\n"
        "    if args.topic_id not in WORK:\n"
        "        raise SystemExit(f'unknown topic: {args.topic_id}')\n"
        "    time.sleep(DELAY_SECONDS)\n"
        "    print(json.dumps(WORK[args.topic_id], indent=2))\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )


def _clean(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("topic_*"):
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    for old in out.glob("module_*.py"):
        old.unlink()
    for name in ["ground_truth.json", "index.md", "work_probe.py"]:
        path = out / name
        if path.exists():
            path.unlink()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topics", type=int, default=8)
    p.add_argument("--distractors", type=int, default=8)
    p.add_argument("--work-delay", type=float, default=0.0, help="seconds each work_probe.py call waits")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "corpus"))
    args = p.parse_args()

    if args.topics < 1:
        raise SystemExit("--topics must be at least 1")
    if args.distractors < 0:
        raise SystemExit("--distractors must be at least 0")
    if args.work_delay < 0:
        raise SystemExit("--work-delay must be at least 0")

    out = Path(args.out)
    _clean(out)
    topics = [_topic(i, args.distractors, args.work_delay) for i in range(args.topics)]
    ground = {}
    for topic in topics:
        topic_dir = out / topic["id"]
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "packet.md").write_text(_packet(topic), encoding="utf-8")
        (topic_dir / "questions.md").write_text(_questions(topic), encoding="utf-8")
        ground[topic["id"]] = {
            "title": topic["title"],
            "work_delay": topic["work_delay"],
            "facts": topic["facts"],
        }

    (out / "index.md").write_text(_index(topics), encoding="utf-8")
    if args.work_delay > 0:
        (out / "work_probe.py").write_text(_work_probe_source(topics, args.work_delay), encoding="utf-8")
    (out / "ground_truth.json").write_text(json.dumps(ground, indent=2), encoding="utf-8")
    total = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    print(f"wrote {len(topics)} topics to {out} ({total:,} bytes total)")
    print(f"ground truth: {out / 'ground_truth.json'}")


if __name__ == "__main__":
    main()
