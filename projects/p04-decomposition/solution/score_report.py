"""Score P04 release-readiness reports against the tutorial rubric."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RubricItem:
    id: str
    priority: str
    title: str
    patterns: tuple[str, ...]


RUBRIC_ITEMS = [
    RubricItem(
        id="agent_canvas_prereq",
        priority="P0",
        title="Identifies agent-canvas as a required external repo/prerequisite",
        patterns=(
            r"agent-canvas.{0,180}(missing|not listed|not stated|undocumented|required external|prerequisite)",
            r"(missing|not listed|not stated|undocumented|required external).{0,180}agent-canvas",
        ),
    ),
    RubricItem(
        id="agent_server_running",
        priority="P0",
        title="Identifies that SDK scripts require a running agent server",
        patterns=(
            r"(agent server|agent-server).{0,180}(must be running|undocumented|connection refused|already running|server dependency)",
            r"(must be running|connection refused|undocumented).{0,180}(agent server|agent-server)",
        ),
    ),
    RubricItem(
        id="api_key_validation",
        priority="P0",
        title="Identifies weak or late LLM_API_KEY validation",
        patterns=(
            r"(llm_api_key|api key).{0,180}(validation|empty|not set|too late|missing)",
            r"(validation|empty|not set|too late|missing).{0,180}(llm_api_key|api key)",
        ),
    ),
    RubricItem(
        id="docker_requirement",
        priority="P0",
        title="Identifies Docker/P06-P07 requirement or dockerless risk clarity",
        patterns=(
            r"docker.{0,180}(required|hidden|buried|p06-p07|p06.*p07|real work)",
            r"(required|hidden|buried|p06-p07|p06.*p07|real work).{0,180}docker",
        ),
    ),
    RubricItem(
        id="correct_release_verdict",
        priority="P0",
        title="Gives a not-ready/do-not-release verdict when blockers are present",
        patterns=(r"not ready|do not release|not release publicly|not ready for public release",),
    ),
    RubricItem(
        id="safety_warning_prominence",
        priority="P1",
        title="Checks prominence of dockerless safety warnings",
        patterns=(
            r"(safety|dockerless|danger).{0,180}(warning|prominent|earlier|banner|placement)",
            r"(warning|prominent|earlier|banner|placement).{0,180}(safety|dockerless|danger)",
        ),
    ),
    RubricItem(
        id="project_title_consistency",
        priority="P1",
        title="Checks project title/name/capitalization consistency",
        patterns=(
            r"(title|project names|capitalization).{0,180}(inconsistent|consistency)",
            r"(inconsistent|consistency).{0,180}(title|project names|capitalization)",
        ),
    ),
    RubricItem(
        id="workspace_dir_default",
        priority="P1",
        title="Checks ambiguous WORKSPACE_DIR/default working directory behavior",
        patterns=(
            r"(workspace_dir|working directory).{0,180}(default|ambiguous|explicit)",
            r"(default|ambiguous|explicit).{0,180}(workspace_dir|working directory)",
        ),
    ),
    RubricItem(
        id="dependency_clarity",
        priority="P1",
        title="Checks per-project package/dependency clarity",
        patterns=(
            r"(dependencies|package|--with).{0,180}(unclear|ambiguous|document)",
            r"(unclear|ambiguous|document).{0,180}(dependencies|package|--with)",
        ),
    ),
]


def parse_score_spec(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        label, _, raw_path = spec.partition("=")
        return label.strip() or Path(raw_path).stem, Path(raw_path).expanduser()
    path = Path(spec).expanduser()
    return path.parent.name or path.stem, path


def matches_rubric_item(text: str, item: RubricItem) -> bool:
    return any(re.search(pattern, text, flags=re.DOTALL) for pattern in item.patterns)


def declared_p0_count(text: str) -> int | None:
    head = text[:2500].lower()
    if "no critical blockers (p0)" in head or "no p0" in head:
        return 0
    patterns = [
        r"(\d+)\s+critical\s+\(p0\)",
        r"(\d+)\s+p0\s+(?:issues|blockers|findings)",
    ]
    for pattern in patterns:
        match = re.search(pattern, head)
        if match:
            return int(match.group(1))
    return None


def p0_table_count(text: str) -> int:
    return len(re.findall(r"^\|\s*P0-\d+\s*\|", text, flags=re.MULTILINE))


def score_report(report_path: Path) -> dict:
    if not report_path.exists():
        return {
            "path": report_path,
            "error": f"Report does not exist: {report_path}",
        }
    text = report_path.read_text(encoding="utf-8")
    lowered = text.lower()
    hits = [item for item in RUBRIC_ITEMS if matches_rubric_item(lowered, item)]
    misses = [item for item in RUBRIC_ITEMS if item not in hits]
    declared = declared_p0_count(text)
    table_count = p0_table_count(text)
    count_ok = declared is None or declared == table_count
    return {
        "path": report_path,
        "hits": hits,
        "misses": misses,
        "declared_p0": declared,
        "table_p0": table_count,
        "count_ok": count_ok,
        "line_count": len(text.splitlines()),
    }


def print_scorecards(specs: list[tuple[str, Path]]) -> None:
    if not specs:
        return
    print("\n" + "=" * 92)
    print("Rubric scorecard")
    print("-" * 92)
    print(
        f"{'Report':<24} {'Coverage':>10} {'P0 rows':>8} "
        f"{'Declared P0':>12} {'Count OK':>9} {'Lines':>7}"
    )
    print("-" * 92)
    scored = []
    for label, path in specs:
        result = score_report(path)
        scored.append((label, result))
        if "error" in result:
            print(f"{label:<24} ERROR: {result['error']}")
            continue
        declared = "n/a" if result["declared_p0"] is None else str(result["declared_p0"])
        print(
            f"{label:<24} {len(result['hits']):>3}/{len(RUBRIC_ITEMS):<6} "
            f"{result['table_p0']:>8} {declared:>12} "
            f"{'yes' if result['count_ok'] else 'no':>9} {result['line_count']:>7}"
        )

    print("\nMissed rubric items:")
    for label, result in scored:
        if "error" in result:
            continue
        if not result["misses"] and result["count_ok"]:
            print(f"- {label}: none")
            continue
        for item in result["misses"]:
            print(f"- {label}: MISS {item.priority} {item.id} - {item.title}")
        if not result["count_ok"]:
            print(
                f"- {label}: FAIL report_count_consistency - declared "
                f"{result['declared_p0']} P0 issues but table lists {result['table_p0']}"
            )
    print("=" * 92)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score P04 release-readiness reports.")
    parser.add_argument(
        "reports",
        nargs="*",
        metavar="LABEL=PATH",
        help="Report path, optionally prefixed with a label.",
    )
    parser.add_argument(
        "--score-report",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Report path, optionally prefixed with a label.",
    )
    args = parser.parse_args()
    specs = [*args.reports, *args.score_report]
    if not specs:
        parser.error("provide at least one report path")
    print_scorecards([parse_score_spec(spec) for spec in specs])


if __name__ == "__main__":
    main()
