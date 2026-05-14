"""Compare two P05 event traces.

Accepts traces saved by run_memory.py or raw /events/search JSON payloads.

Run with:
    uv run python compare_traces.py no-memory=path/to/no-memory-events.json with-memory=path/to/with-memory-events.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOOL_HINTS = (
    "terminal",
    "file_editor",
    "task_tracker",
    "browser",
    "execute_bash",
    "str_replace_editor",
)

DISCOVERY_PATTERNS = (
    r"\bpwd\b",
    r"\bls\b",
    r"\bfind\b",
    r"\btree\b",
    r"directory layout",
    r"repo structure",
    r"package\.json",
    r"readme\.md",
    r"development\.md",
    r"\bsrc/",
    r"\bscripts/",
)


def parse_spec(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        label, _, raw_path = spec.partition("=")
        path = Path(raw_path).expanduser()
        return label.strip() or path.stem, path
    path = Path(spec).expanduser()
    return path.stem, path


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Trace does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_events(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return extract_events(value)
        data = payload.get("data")
        if isinstance(data, (dict, list)):
            return extract_events(data)
    raise SystemExit("Could not find an event list in the trace JSON")


def nested_get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def metric_number(payload: Any, *paths: tuple[str, ...]) -> float | None:
    if not isinstance(payload, dict):
        return None
    for path in paths:
        value = nested_get(payload, path)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def flatten_text(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False).lower()
    except TypeError:
        return str(value).lower()


def event_type(event: Any) -> str:
    if isinstance(event, dict):
        for key in ("type", "event_type", "kind"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
        for key in ("action", "observation"):
            nested = event.get(key)
            if isinstance(nested, dict):
                for nested_key in ("type", "event_type", "kind"):
                    value = nested.get(nested_key)
                    if isinstance(value, str) and value:
                        return value
    return type(event).__name__


def tool_name(event: Any) -> str | None:
    if isinstance(event, dict):
        for key in ("tool", "tool_name", "name"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
        for key in ("action", "observation"):
            nested = event.get(key)
            if isinstance(nested, dict):
                value = tool_name(nested)
                if value:
                    return value

    text = flatten_text(event)
    for hint in TOOL_HINTS:
        if hint in text:
            return hint
    return None


def is_agent_turn(event: Any) -> bool:
    event_text = flatten_text(event)
    event_kind = event_type(event).lower()
    return (
        "agent" in event_kind
        or "assistant" in event_kind
        or '"source": "agent"' in event_text
        or '"source":"agent"' in event_text
    )


def is_compaction(event: Any) -> bool:
    text = flatten_text(event)
    return "compact" in text or "condens" in text


def is_discovery_event(event: Any) -> bool:
    text = flatten_text(event)
    return any(re.search(pattern, text) for pattern in DISCOVERY_PATTERNS)


def summarize(label: str, path: Path) -> dict[str, Any]:
    payload = load_json(path)
    events = extract_events(payload)
    event_types = Counter(event_type(event) for event in events)
    tool_names = [name for event in events if (name := tool_name(event))]
    tools = Counter(tool_names)
    prompt_tokens = metric_number(
        payload,
        ("metrics", "prompt_tokens"),
        ("metrics", "tokens_in"),
        ("metrics", "accumulated_prompt_tokens"),
        ("metrics", "accumulated_token_usage", "prompt_tokens"),
    )
    cost = metric_number(payload, ("metrics", "cost"), ("metrics", "accumulated_cost"))
    return {
        "label": label,
        "path": path,
        "events": len(events),
        "agent_turns": sum(1 for event in events if is_agent_turn(event)),
        "tool_calls": len(tool_names),
        "discovery_events": sum(1 for event in events if is_discovery_event(event)),
        "compaction_events": sum(1 for event in events if is_compaction(event)),
        "tokens_in": prompt_tokens,
        "cost": cost,
        "event_types": event_types,
        "tools": tools,
    }


def fmt_number(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    if digits:
        return f"{value:.{digits}f}"
    return str(int(value))


def fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):.4f}"


def print_table(summaries: list[dict[str, Any]]) -> None:
    print("\nTrace comparison")
    print("-" * 92)
    print(
        f"{'Trace':<18} {'Events':>7} {'Agent':>7} {'Tools':>7} "
        f"{'Discovery':>10} {'Compacts':>9} {'Tokens in':>12} {'Cost':>9}"
    )
    print("-" * 92)
    for summary in summaries:
        print(
            f"{summary['label']:<18} {summary['events']:>7} "
            f"{summary['agent_turns']:>7} {summary['tool_calls']:>7} "
            f"{summary['discovery_events']:>10} {summary['compaction_events']:>9} "
            f"{fmt_number(summary['tokens_in']):>12} "
            f"{fmt_money(summary['cost']):>9}"
        )
    print("-" * 92)


def pct_delta(delta: float, base: float | None) -> str:
    if not base:
        return ""
    return f" ({delta / base * 100:+.0f}%)"


def print_delta(before: dict[str, Any], after: dict[str, Any]) -> None:
    print("\nDelta: second trace minus first trace")
    for label, key in [
        ("Events", "events"),
        ("Agent-turn proxy", "agent_turns"),
        ("Tool-call proxy", "tool_calls"),
        ("Likely discovery events", "discovery_events"),
        ("Compaction events", "compaction_events"),
    ]:
        delta = after[key] - before[key]
        print(f"- {label}: {delta:+}{pct_delta(delta, before[key])}")

    for label, key, digits in [
        ("Tokens in", "tokens_in", 0),
        ("Cost", "cost", 4),
    ]:
        if before[key] is None or after[key] is None:
            continue
        delta = after[key] - before[key]
        value = fmt_money(delta) if key == "cost" else fmt_number(delta, digits)
        print(f"- {label}: {value}{pct_delta(delta, before[key])}")


def print_counter_delta(name: str, before: Counter[str], after: Counter[str]) -> None:
    changes = []
    for key in sorted(set(before) | set(after)):
        delta = after[key] - before[key]
        if delta:
            changes.append((abs(delta), delta, key))
    if not changes:
        return
    print(f"\nTop {name} deltas")
    for _, delta, key in sorted(changes, reverse=True)[:8]:
        print(f"- {key}: {delta:+}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare no-memory and with-memory P05 traces.")
    parser.add_argument("traces", nargs=2, metavar="LABEL=PATH")
    args = parser.parse_args()

    summaries = [summarize(label, path) for label, path in map(parse_spec, args.traces)]
    print_table(summaries)
    print_delta(summaries[0], summaries[1])
    print_counter_delta("event-type", summaries[0]["event_types"], summaries[1]["event_types"])
    print_counter_delta("tool", summaries[0]["tools"], summaries[1]["tools"])
    print("\nUse the discovery row as a proxy, then inspect the raw trace before claiming causality.")


if __name__ == "__main__":
    main()
