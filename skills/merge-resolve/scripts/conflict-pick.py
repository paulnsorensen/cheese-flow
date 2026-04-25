#!/usr/bin/env python3
"""
Pick ours or theirs for conflict hunks.
For file types not handled by mergiraf (shell scripts, config files, etc.).
"""

import argparse
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from git_utils import run_git, parse_conflict_hunks


def resolve_hunks(content: str, strategy: str, grep_pattern: str = None) -> str:
    """
    Resolve conflict hunks using the specified strategy.
    
    Args:
        content: File content with conflict markers
        strategy: 'ours' or 'theirs'
        grep_pattern: If provided, only resolve hunks matching this pattern
    
    Returns:
        Resolved content
    """
    lines = content.split("\n")
    result = []
    
    in_conflict = False
    current_section = None  # 'ours', 'base', 'theirs'
    ours_lines = []
    theirs_lines = []
    conflict_text = []  # Full conflict text for grep matching
    conflict_start = 0
    
    for i, line in enumerate(lines):
        if line.startswith("<<<<<<<"):
            in_conflict = True
            current_section = "ours"
            ours_lines = []
            theirs_lines = []
            conflict_text = [line]
            conflict_start = i
        elif line.startswith("|||||||") and in_conflict:
            current_section = "base"
            conflict_text.append(line)
        elif line.startswith("=======") and in_conflict:
            current_section = "theirs"
            conflict_text.append(line)
        elif line.startswith(">>>>>>>") and in_conflict:
            conflict_text.append(line)
            
            # Check if we should resolve this hunk
            should_resolve = True
            if grep_pattern:
                full_conflict = "\n".join(conflict_text)
                should_resolve = re.search(grep_pattern, full_conflict) is not None
            
            if should_resolve:
                # Apply resolution
                if strategy == "ours":
                    result.extend(ours_lines)
                else:
                    result.extend(theirs_lines)
            else:
                # Keep conflict markers (leave for manual resolution)
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
    
    # Validate strategy
    if args.ours and args.theirs:
        print("Error: Cannot use both --ours and --theirs")
        return 1
    
    if not args.ours and not args.theirs:
        print("Error: Must specify --ours or --theirs")
        return 1
    
    strategy = "ours" if args.ours else "theirs"
    
    # Read file
    try:
        content = Path(args.file).read_text()
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}")
        return 1
    
    # Check for conflicts
    if "<<<<<<" not in content:
        print(f"No conflict markers found in {args.file}")
        return 0
    
    # Resolve
    resolved = resolve_hunks(content, strategy, args.grep)
    
    # Check if all conflicts resolved
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
            # Stage the file
            run_git(["add", args.file])
            print(f"Resolved and staged {args.file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
