#!/usr/bin/env python3
"""age-fixture-diff — compare a /age dim agent's output against a fixture.

Validates `<run>/<dim>.json` against `tests/age-fixtures/<dim>/expected.json`
using the tolerances locked in `.claude/specs/age-extraction.md` §Validation:

- `dimension` — exact match
- `bucket`    — exact match
- `narrative` — Levenshtein-equivalent ratio (difflib.SequenceMatcher) ≥ 0.6
- `anchor.start` line number — within ±1 of expected (hash ignored)

Stdlib-only. Exits 0 when every expected observation is matched, 1 otherwise.
JSON-on-stdout summarises matches and misses for the `just test-age-fixtures`
gate.

    python python/tools/age_fixture_diff.py <actual.json> <expected.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

NARRATIVE_RATIO = 0.6
ANCHOR_TOLERANCE = 1


def _line_for(anchor: object) -> int | None:
    if not isinstance(anchor, dict):
        return None
    start = anchor.get("start")
    if not isinstance(start, str) or ":" not in start:
        return None
    head, _, _ = start.partition(":")
    try:
        return int(head)
    except ValueError:
        return None


def _candidate_score(actual: dict, expected: dict) -> float:
    if actual.get("bucket") != expected.get("bucket"):
        return 0.0
    actual_line = _line_for(actual.get("anchor"))
    expected_line = _line_for(expected.get("anchor"))
    if actual_line is None or expected_line is None:
        return 0.0
    if abs(actual_line - expected_line) > ANCHOR_TOLERANCE:
        return 0.0
    ratio = SequenceMatcher(
        None,
        str(actual.get("narrative", "")),
        str(expected.get("narrative", "")),
    ).ratio()
    if ratio < NARRATIVE_RATIO:
        return 0.0
    return ratio


def _match_expected(
    expected_obs: dict, available_actual: list[dict]
) -> tuple[dict, int] | tuple[None, int]:
    """Return (match_dict, best_idx) or (None, -1). Caller must remove best_idx."""
    expected_id = expected_obs.get("id")
    # Prefer exact id match first.
    for idx, actual in enumerate(available_actual):
        if actual.get("id") == expected_id:
            score = _candidate_score(actual, expected_obs)
            if score > 0.0:
                return {
                    "expected_id": expected_id,
                    "matched_id": actual.get("id"),
                    "narrative_ratio": round(score, 3),
                    "expected_anchor": expected_obs.get("anchor"),
                    "matched_anchor": actual.get("anchor"),
                }, idx
    # Fall back to best fuzzy match among remaining actuals.
    best_idx = -1
    best_score = 0.0
    for idx, actual in enumerate(available_actual):
        score = _candidate_score(actual, expected_obs)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0:
        return None, -1
    actual = available_actual[best_idx]
    return {
        "expected_id": expected_id,
        "matched_id": actual.get("id"),
        "narrative_ratio": round(best_score, 3),
        "expected_anchor": expected_obs.get("anchor"),
        "matched_anchor": actual.get("anchor"),
    }, best_idx


def diff(actual: dict, expected: dict) -> dict:
    if actual.get("dimension") != expected.get("dimension"):
        return {
            "ok": False,
            "reason": "dimension mismatch",
            "actual_dimension": actual.get("dimension"),
            "expected_dimension": expected.get("dimension"),
        }
    expected_obs = expected.get("observations") or []
    # Work on a mutable copy so each actual is consumed at most once.
    available_actual: list[dict] = list(actual.get("observations") or [])
    matches: list[dict] = []
    misses: list[dict] = []
    for obs in expected_obs:
        match, best_idx = _match_expected(obs, available_actual)
        if match is None:
            misses.append({"expected_id": obs.get("id"), "anchor": obs.get("anchor")})
        else:
            matches.append(match)
            available_actual.pop(best_idx)
    return {
        "ok": not misses,
        "dimension": expected.get("dimension"),
        "matches": matches,
        "misses": misses,
        "actual_count": len(actual.get("observations") or []),
        "expected_count": len(expected_obs),
    }


def _load(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="age-fixture-diff")
    parser.add_argument("actual", type=Path)
    parser.add_argument("expected", type=Path)
    ns = parser.parse_args(argv)
    result = diff(_load(ns.actual), _load(ns.expected))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
