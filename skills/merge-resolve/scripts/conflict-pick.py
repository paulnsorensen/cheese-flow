#!/usr/bin/env python3
"""
Pick ours or theirs for conflict hunks.
For file types not handled by mergiraf (shell scripts, config files, etc.).
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from git_utils import run_git


def resolve_hunks(content: str, strategy: str, grep_pattern: Optional[str] = None) -> str:
    lines = content.split("\n")
    result = []
    
    in_conflict = False
    current_section = None  # 'ours', 'base', 'theirs'
    ours_lines = []
    theirs_lines = []
    conflict_text = []  # Full conflict text for grep matching

    for line in lines:
        if line.startswith("<<<<<<<"):
            in_conflict = True
            current_section = "ours"
            ours_lines = []
            theirs_lines = []
            conflict_text = [line]
        elif line.startswith("|||||||") and in_conflict:
            current_section = "base"
            conflict_text.append(line)
        elif line.startswith("=======") and in_conflict:
            current_section = "theirs"
            conflict_text.append(line)
        elif line.startswith(">>>>>>>") and in_conflict:
            conflict_text.append(line)
            
            should_resolve = True
            if grep_pattern:
                full_conflict = "\n".join(conflict_text)
                should_resolve = re.search(grep_pattern, full_conflict) is not None

            if should_resolve:
                if strategy == "ours":
                    result.extend(ours_lines)
                else:
                    result.extend(theirs_lines)
            else:
                # keep conflict markers — doesn't match grep filter
                result.extend(conflict_text)
            
            in_conflict = False
            current_section = None
        elif in_conflict:
            conflict_text.append(line)
            if current_section == "ours":
                ours_lines.append(line)
            elif current_section == "theirs":
                theirs_lines.append(line)
            # Ignore base section
        else:
            result.append(line)

    if in_conflict:
        # Unterminated conflict — preserve the partial markers to avoid silent data loss
        result.extend(conflict_text)

    return "\n".join(result)


def main():
    parser = argparse.ArgumentParser(
        description="Pick ours or theirs for conflict hunks"
    )
    parser.add_argument(
        "file",
        help="File to resolve",
    )
    parser.add_argument(
        "--ours",
        action="store_true",
        help="Take our changes for all matching hunks",
    )
    parser.add_argument(
        "--theirs",
        action="store_true",
        help="Take their changes for all matching hunks",
    )
    parser.add_argument(
        "--grep",
        metavar="PATTERN",
        help="Only resolve hunks containing this pattern (regex)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved content without writing",
    )
    
    args = parser.parse_args()

    if args.ours and args.theirs:
        print("Error: Cannot use both --ours and --theirs")
        return 1

    if not args.ours and not args.theirs:
        print("Error: Must specify --ours or --theirs")
        return 1

    strategy = "ours" if args.ours else "theirs"

    try:
        content = Path(args.file).read_text()
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}")
        return 1

    if "<<<<<<" not in content:
        print(f"No conflict markers found in {args.file}")
        return 0

    resolved = resolve_hunks(content, strategy, args.grep)
    has_remaining = "<<<<<<" in resolved

    if args.dry_run:
        print(resolved)
        if has_remaining:
            print(f"\n# Note: Some conflicts remain (not matching --grep pattern)")
    else:
        Path(args.file).write_text(resolved)
        
        if has_remaining:
            print(f"Partially resolved {args.file} - some conflicts remain")
        else:
            add_result = run_git(["add", args.file])
            if add_result.returncode != 0:
                print(f"Error: Resolved but staging failed: {add_result.stderr.strip()}")
                return 1
            print(f"Resolved and staged {args.file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
