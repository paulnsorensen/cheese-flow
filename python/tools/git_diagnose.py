#!/usr/bin/env python3
"""git-diagnose — codebase orientation signals as JSON.

Modeled on Ally Piechowski's "The Git Commands I Run Before Reading Any Code"
(https://piechowski.io/post/git-commands-before-reading-code/, Apr 8 2026):
hotspots, bus factor, bug clusters, velocity, and firefighting frequency.
Plus a per-file `risk` subcommand for the age-history modifier loop.

Stdlib-only. JSON-on-stdout. No third-party deps. Each subcommand prints a
single JSON document so callers can parse without context-polluting raw
git log output.

    python python/tools/git_diagnose.py hotspots --since 1.year.ago --limit 20
    python python/tools/git_diagnose.py bus-factor
    python python/tools/git_diagnose.py bug-clusters
    python python/tools/git_diagnose.py velocity
    python python/tools/git_diagnose.py firefighting
    python python/tools/git_diagnose.py risk path/a.ts path/b.ts
    python python/tools/git_diagnose.py orient
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter

SECONDS_PER_DAY = 86400
DEFAULT_SINCE = "1.year.ago"
DEFAULT_LIMIT = 20
DEFAULT_BUS_LIMIT = 10
FIREFIGHT_RE = re.compile(r"\b(revert|hotfix|emergency|rollback)\b", re.IGNORECASE)


def _run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


# ─── repo-wide commands (Piechowski 1-5) ─────────────────────────────────────


def hotspots(since: str = DEFAULT_SINCE, limit: int = DEFAULT_LIMIT) -> list[dict[str, object]]:
    """Top files by commit count in window (Piechowski cmd 1: code churn)."""
    output = _run_git(["log", f"--since={since}", "--format=", "--name-only"])
    counts = Counter(line for line in output.splitlines() if line.strip())
    return [{"file": f, "changes": n} for f, n in counts.most_common(limit)]


def _parse_shortlog_line(raw: str) -> tuple[int, str] | None:
    line = raw.strip()
    if not line:
        return None
    count_str, _, author = line.partition("\t")
    try:
        return int(count_str.strip()), author.strip()
    except ValueError:
        return None


def bus_factor(limit: int = DEFAULT_BUS_LIMIT) -> list[dict[str, object]]:
    """Contributors by commit count with % share (Piechowski cmd 2: bus factor)."""
    output = _run_git(["shortlog", "-sn", "--no-merges", "--all"])
    parsed = [_parse_shortlog_line(raw) for raw in output.splitlines()]
    rows = sorted((r for r in parsed if r is not None), reverse=True)
    total = sum(n for n, _ in rows) or 1
    return [
        {"author": author, "commits": n, "percent": round(100 * n / total, 1)}
        for n, author in rows[:limit]
    ]


def bug_clusters(limit: int = DEFAULT_LIMIT) -> list[dict[str, object]]:
    """Top files touched by fix/bug/broken commits (Piechowski cmd 3)."""
    output = _run_git(["log", "-i", "-E", "--grep=fix|bug|broken", "--format=", "--name-only"])
    counts = Counter(line for line in output.splitlines() if line.strip())
    return [{"file": f, "bug_changes": n} for f, n in counts.most_common(limit)]


def velocity() -> list[dict[str, object]]:
    """Commits per month across all history (Piechowski cmd 4: project health)."""
    output = _run_git(["log", "--format=%ad", "--date=format:%Y-%m"])
    counts = Counter(line.strip() for line in output.splitlines() if line.strip())
    return [{"month": m, "commits": n} for m, n in sorted(counts.items())]


def firefighting(since: str = DEFAULT_SINCE) -> list[dict[str, object]]:
    """Revert/hotfix/emergency/rollback commits in window (Piechowski cmd 5)."""
    output = _run_git(["log", "--oneline", f"--since={since}"])
    return [
        {"sha": sha, "subject": subject}
        for line in output.splitlines()
        for sha, _, subject in [line.partition(" ")]
        if subject and FIREFIGHT_RE.search(subject)
    ]


# ─── per-file risk (consumed by age-history) ─────────────────────────────────


def _authors_and_changes_90d(path: str) -> tuple[int, int]:
    output = _run_git(["log", "--since=90.days.ago", "--format=%ae", "--", path])
    emails = [line for line in output.splitlines() if line]
    return len(set(emails)), len(emails)


def _revert_count(path: str) -> int:
    output = _run_git(["log", "--format=%s", "--", path])
    return sum(1 for line in output.splitlines() if line.startswith("Revert"))


def _last_change_days(path: str, now_ts: int | None = None) -> int | None:
    output = _run_git(["log", "-1", "--format=%ct", "--", path]).strip()
    if not output:
        return None
    last = int(output)
    now = now_ts if now_ts is not None else int(time.time())
    return max(0, (now - last) // SECONDS_PER_DAY)


def _humanize_staleness(days: int | None) -> str:
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
    authors, changes = _authors_and_changes_90d(path)
    days = _last_change_days(path, now_ts=now_ts)
    return {
        "file": path,
        "authors_90d": authors,
        "changes_90d": changes,
        "reverts": _revert_count(path),
        "last_change_days": -1 if days is None else days,
        "staleness": _humanize_staleness(days),
    }


# ─── orient (bundles all five for Culture's single call) ─────────────────────


def orient() -> dict[str, object]:
    """Run all five Piechowski commands and bundle with a derived summary."""
    h = hotspots()
    bf = bus_factor()
    bc = bug_clusters()
    vel = velocity()
    ff = firefighting()
    hotspot_files = {str(row["file"]) for row in h}
    bug_files = {str(row["file"]) for row in bc}
    intersect = sorted(hotspot_files & bug_files)
    top_pct = bf[0]["percent"] if bf else 0.0
    return {
        "hotspots": h,
        "bus_factor": bf,
        "bug_clusters": bc,
        "velocity": vel,
        "firefighting": ff,
        "summary": {
            "hotspot_count": len(h),
            "bug_cluster_count": len(bc),
            "intersect_hotspot_bug": intersect,
            "top_author_pct": top_pct,
            "firefighting_count": len(ff),
        },
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="git-diagnose")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_h = sub.add_parser("hotspots")
    p_h.add_argument("--since", default=DEFAULT_SINCE)
    p_h.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p_bf = sub.add_parser("bus-factor")
    p_bf.add_argument("--limit", type=int, default=DEFAULT_BUS_LIMIT)
    p_bc = sub.add_parser("bug-clusters")
    p_bc.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    sub.add_parser("velocity")
    p_ff = sub.add_parser("firefighting")
    p_ff.add_argument("--since", default=DEFAULT_SINCE)
    p_risk = sub.add_parser("risk")
    p_risk.add_argument("paths", nargs="+")
    sub.add_parser("orient")
    return parser


def _dispatch(ns: argparse.Namespace) -> object:
    if ns.cmd == "hotspots":
        return hotspots(since=ns.since, limit=ns.limit)
    if ns.cmd == "bus-factor":
        return bus_factor(limit=ns.limit)
    if ns.cmd == "bug-clusters":
        return bug_clusters(limit=ns.limit)
    if ns.cmd == "velocity":
        return velocity()
    if ns.cmd == "firefighting":
        return firefighting(since=ns.since)
    if ns.cmd == "risk":
        return [risk_for(p) for p in ns.paths]
    if ns.cmd == "orient":
        return orient()


def main(argv: list[str]) -> int:
    ns = _build_parser().parse_args(argv)
    print(json.dumps(_dispatch(ns)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
