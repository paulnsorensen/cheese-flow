#!/usr/bin/env python3
"""
Batch conflict resolution using mergiraf.
Extracts 3-way inputs and runs mergiraf on all conflicted files.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from git_utils import (
    get_conflicted_files,
    extract_stages,
    is_mergiraf_supported,
    run_git,
)


def check_mergiraf_available() -> bool:
    """Check if mergiraf is available."""
    try:
        result = subprocess.run(["mergiraf", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def resolve_file(path: str, dry_run: bool = True, verbose: bool = False) -> dict:
    """
    Attempt to resolve a single file using mergiraf.
    Returns dict with status, message, and whether it was resolved.
    """
    result = {
        "path": path,
        "supported": is_mergiraf_supported(path),
        "resolved": False,
        "message": "",
    }
    
    if not result["supported"]:
        result["message"] = f"File type not supported by mergiraf"
        return result
    
    # Extract 3-way inputs
    base, ours, theirs = extract_stages(path)
    
    if base is None or ours is None or theirs is None:
        result["message"] = "Could not extract all three stages from git"
        return result
    
    # Write to temp files
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base")
        ours_path = os.path.join(tmpdir, "ours")
        theirs_path = os.path.join(tmpdir, "theirs")
        merged_path = os.path.join(tmpdir, "merged")
        
        Path(base_path).write_text(base)
        Path(ours_path).write_text(ours)
        Path(theirs_path).write_text(theirs)
        
        # Run mergiraf
        cmd = ["mergiraf", "merge", base_path, ours_path, theirs_path, "-o", merged_path, "-p", path]
        
        if verbose:
            env = os.environ.copy()
            env["RUST_LOG"] = "mergiraf=debug"
            merge_result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if merge_result.stderr:
                print(f"DEBUG {path}:\n{merge_result.stderr}", file=sys.stderr)
        else:
            merge_result = subprocess.run(cmd, capture_output=True, text=True)
        
        if merge_result.returncode != 0:
            result["message"] = f"Mergiraf failed: {merge_result.stderr.strip()}"
            return result
        
        # Check if merged output has conflict markers
        try:
            merged_content = Path(merged_path).read_text()
        except FileNotFoundError:
            result["message"] = "Mergiraf did not produce output file"
            return result
        
        has_conflicts = "<<<<<<" in merged_content or "======" in merged_content
        
        if has_conflicts:
            result["message"] = "Mergiraf could not fully resolve - conflicts remain"
            return result
        
        # Clean merge - apply if not dry run
        result["resolved"] = True
        
        if dry_run:
            result["message"] = "Would resolve cleanly (dry run)"
        else:
            Path(path).write_text(merged_content)
            run_git(["add", path])
            result["message"] = "Resolved and staged"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Batch resolve conflicts using mergiraf"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview resolutions without applying them",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply resolutions (opposite of --dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show mergiraf debug output",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to resolve (default: all conflicted files)",
    )
    
    args = parser.parse_args()
    
    # Check mergiraf availability
    if not check_mergiraf_available():
        print("Error: mergiraf not found. Install with: cargo install mergiraf")
        return 1
    
    # Determine mode
    dry_run = not args.apply
    if args.dry_run and args.apply:
        print("Error: Cannot use both --dry-run and --apply")
        return 1
    
    # Get files to process
    if args.files:
        files = args.files
    else:
        files = get_conflicted_files()
    
    if not files:
        print("No conflicted files found.")
        return 0
    
    # Process each file
    results = []
    for path in files:
        result = resolve_file(path, dry_run=dry_run, verbose=args.verbose)
        results.append(result)
    
    # Output summary
    resolved = [r for r in results if r["resolved"]]
    unresolved = [r for r in results if not r["resolved"]]
    
    print(f"\n# Batch Resolution Summary")
    print(f"Mode: {'dry-run' if dry_run else 'apply'}")
    print(f"Total: {len(results)} | Resolved: {len(resolved)} | Unresolved: {len(unresolved)}")
    print()
    
    if resolved:
        print("## Resolved")
        for r in resolved:
            print(f"  ✓ {r['path']}: {r['message']}")
        print()
    
    if unresolved:
        print("## Needs Manual Resolution")
        for r in unresolved:
            print(f"  ✗ {r['path']}: {r['message']}")
        print()
    
    if dry_run and resolved:
        print("Run with --apply to apply these resolutions.")
    
    return 0 if not unresolved else 1


if __name__ == "__main__":
    sys.exit(main())
