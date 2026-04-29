#!/usr/bin/env python3
"""git-file-risk — emit per-file git risk signals as JSON.

Consumed by the age-history sub-agent to compute risk modifiers without
context-polluting raw `git log` output. Deterministic, fast, batch call:

    python python/tools/git_file_risk.py path/a.ts path/b.ts

Stdout is a JSON array of objects with this shape:

    {
      "file": "path/a.ts",
      "authors_90d": <int>,
      "changes_90d": <int>,
      "reverts": <int>,
      "last_change_days": <int>,        // -1 if file is untracked
      "staleness": "<human string>"
    }
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

SECONDS_PER_DAY = 86400


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def authors_and_changes_90d(path: str) -> tuple[int, int]:
    output = _run_git(["log", "--since=90.days.ago", "--format=%ae", "--", path])
    emails = [line for line in output.splitlines() if line]
    return len(set(emails)), len(emails)


def revert_count(path: str) -> int:
    output = _run_git(["log", "--format=%s", "--", path])
    return sum(1 for line in output.splitlines() if line.startswith("Revert"))


def last_change_days(path: str, now_ts: int | None = None) -> int | None:
    output = _run_git(["log", "-1", "--format=%ct", "--", path]).strip()
    if not output:
        return None
    last = int(output)
    now = now_ts if now_ts is not None else int(time.time())
    return max(0, (now - last) // SECONDS_PER_DAY)


def humanize_staleness(days: int | None) -> str:
    if days is None:
        return "untracked"
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = max(1, round(days / 30))
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(1, round(days / 365))
    return f"{years} year{'s' if years != 1 else ''} ago"


def risk_for(path: str, now_ts: int | None = None) -> dict[str, object]:
    authors, changes = authors_and_changes_90d(path)
    days = last_change_days(path, now_ts=now_ts)
    return {
        "file": path,
        "authors_90d": authors,
        "changes_90d": changes,
        "reverts": revert_count(path),
        "last_change_days": -1 if days is None else days,
        "staleness": humanize_staleness(days),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: git-file-risk <file>...", file=sys.stderr)
        return 2
    print(json.dumps([risk_for(p) for p in argv]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
