"""P07a starter - scaffold a repeated-run critic evaluation.

Run:
    uv run python evaluate.py --dry-run

TODO:
    1. Build the no-critic agent config.
    2. Build the critic agent config with APIBasedCritic + IterativeRefinementConfig.
    3. Run N fresh Docker workspaces per config.
    4. Score each workspace with the same deterministic rubric.
    5. Print pass-rate and cost-per-pass.
"""

from __future__ import annotations

import argparse
import os


WORDSTATS_RUBRIC = """\
Pass only if all five checks are true:
1. `wordstats/stats.py` exposes `analyze_file(filepath)`.
2. `wordstats/cli.py` runs as `python wordstats/cli.py <file>`.
3. Empty files return zeros.
4. Hyphenated words and contractions count as words; numbers do not.
5. Missing files raise `FileNotFoundError` and the CLI exits non-zero.
"""

WORDSTATS_TASK = f"""\
Create a Python word statistics tool called `wordstats`.

Required files:
- `wordstats/stats.py`
- `wordstats/cli.py`

`stats.py` must define `analyze_file(filepath) -> dict` with exactly these keys:
- `lines`
- `words`
- `chars`
- `unique_words`

Rules:
- Empty files return all zeros.
- Hyphenated words count as one word.
- Contractions like `don't` count as one word.
- Numbers such as `42` and `3.14` are not words.
- Missing files raise `FileNotFoundError`.

Rubric:
{WORDSTATS_RUBRIC}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P07a critic evaluation scaffold.")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--config", choices=["no-critic", "critic", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configs = ["no-critic", "critic"] if args.config == "both" else [args.config]
    print("P07a repeated-run evaluator scaffold")
    print(f"Configs: {', '.join(configs)}")
    print(f"Trials per config: {args.trials}")
    print(f"Model: {os.environ.get('LLM_MODEL', 'anthropic/claude-haiku-4-5-20251001')}")
    print("\nTask prompt:")
    print(WORDSTATS_TASK)
    if not args.dry_run:
        print("\nTODO: fill in run_trial(), score_workspace(), and summarize().")
        print("See ../solution/evaluate.py for a complete reference implementation.")


if __name__ == "__main__":
    main()
