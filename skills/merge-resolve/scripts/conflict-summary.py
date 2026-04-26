#!/usr/bin/env python3
"""Conflict summary script for merge-resolve skill."""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from git_utils import (
    get_conflicted_files,
    is_mergiraf_supported,
    parse_conflict_hunks,
    get_surrounding_context,
    get_file_extension,
)


def summarize_file(path: str, context_lines: int = 3) -> dict:
    try:
        content = Path(path).read_text()
    except Exception as e:
        return {"path": path, "error": str(e)}

    ext = get_file_extension(path)
    hunks = parse_conflict_hunks(content)

    summary = {
        "path": path,
        "extension": ext,
        "mergiraf_supported": is_mergiraf_supported(path),
        "hunk_count": len(hunks),
        "hunks": [],
    }

    for i, hunk in enumerate(hunks, 1):
        before, after = get_surrounding_context(
            content, hunk["start_line"], hunk["end_line"], context_lines
        )

        hunk_summary = {
            "hunk_number": i,
            "lines": f"{hunk['start_line']}-{hunk['end_line']}",
            "ours": hunk["ours"],
            "theirs": hunk["theirs"],
            "has_base": bool(hunk["base"]),
            "context_before": before,
            "context_after": after,
        }

        if hunk["base"]:
            hunk_summary["base"] = hunk["base"]

        summary["hunks"].append(hunk_summary)

    if summary["mergiraf_supported"] and summary["hunk_count"] > 0:
        summary["recommendation"] = "Try batch-resolve.py --dry-run to check if mergiraf can resolve"
    elif ext in ("lock", "sum") or "lock" in path.lower():
        summary["recommendation"] = "Use lockfile-resolve.py for lockfile conflicts"
    elif ext in ("sh", "bash", "zsh", "yaml", "yml", "json", "md"):
        summary["recommendation"] = "Use conflict-pick.py to choose ours/theirs per hunk"
    else:
        summary["recommendation"] = "Manual resolution with git mergetool recommended"

    return summary


def format_text_output(summaries: list) -> str:
    if not summaries:
        return "No conflicted files found."

    lines = []
    lines.append(f"# Conflict Summary — {len(summaries)} file(s)")
    lines.append("")

    for summary in summaries:
        if "error" in summary:
            lines.append(f"## {summary['path']}")
            lines.append(f"Error: {summary['error']}")
            lines.append("")
            continue

        mergiraf_status = "✓ supported" if summary["mergiraf_supported"] else "✗ not supported"
        lines.append(f"## {summary['path']}")
        lines.append(f"Extension: .{summary['extension']} | Mergiraf: {mergiraf_status} | Hunks: {summary['hunk_count']}")
        lines.append("")

        for hunk in summary["hunks"]:
            lines.append(f"### Hunk {hunk['hunk_number']} (lines {hunk['lines']})")

            if hunk["context_before"]:
                lines.append("Context before:")
                for ctx in hunk["context_before"]:
                    lines.append(f"  {ctx}")

            lines.append("OURS:")
            for line in hunk["ours"][:10]:  # cap at 10 lines
                lines.append(f"  + {line}")
            if len(hunk["ours"]) > 10:
                lines.append(f"  ... ({len(hunk['ours']) - 10} more lines)")

            if hunk["has_base"]:
                lines.append("BASE:")
                for line in hunk.get("base", [])[:5]:
                    lines.append(f"  | {line}")
                if len(hunk.get("base", [])) > 5:
                    lines.append(f"  ... ({len(hunk['base']) - 5} more lines)")

            lines.append("THEIRS:")
            for line in hunk["theirs"][:10]:
                lines.append(f"  - {line}")
            if len(hunk["theirs"]) > 10:
                lines.append(f"  ... ({len(hunk['theirs']) - 10} more lines)")

            if hunk["context_after"]:
                lines.append("Context after:")
                for ctx in hunk["context_after"]:
                    lines.append(f"  {ctx}")

            lines.append("")

        lines.append(f"**Recommendation:** {summary['recommendation']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Summarize merge conflicts with structured output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of text",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=3,
        help="Lines of context to show (default: 3)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to summarize (default: all conflicted files)",
    )

    args = parser.parse_args()

    files = args.files if args.files else get_conflicted_files()

    if not files:
        if args.json:
            print(json.dumps({"files": [], "message": "No conflicted files found"}))
        else:
            print("No conflicted files found.")
        return 0

    summaries = [summarize_file(f, args.context) for f in files]

    if args.json:
        print(json.dumps({"files": summaries}, indent=2))
    else:
        print(format_text_output(summaries))

    return 0


if __name__ == "__main__":
    sys.exit(main())
