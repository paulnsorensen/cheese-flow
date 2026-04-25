#!/usr/bin/env python3
"""
Lockfile conflict resolution.
Takes one side and regenerates the lockfile from the manifest.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from git_utils import (
    get_conflicted_files,
    detect_lockfile_type,
    run_git,
)


# Map lockfile types to regeneration commands and manifest files
LOCKFILE_CONFIG = {
    "cargo": {
        "manifest": "Cargo.toml",
        "lockfile": "Cargo.lock",
        "regen_cmd": ["cargo", "generate-lockfile"],
    },
    "npm": {
        "manifest": "package.json",
        "lockfile": "package-lock.json",
        "regen_cmd": ["npm", "install", "--package-lock-only"],
    },
    "yarn": {
        "manifest": "package.json",
        "lockfile": "yarn.lock",
        "regen_cmd": ["yarn", "install", "--mode", "update-lockfile"],
    },
    "pnpm": {
        "manifest": "package.json",
        "lockfile": "pnpm-lock.yaml",
        "regen_cmd": ["pnpm", "install", "--lockfile-only"],
    },
    "poetry": {
        "manifest": "pyproject.toml",
        "lockfile": "poetry.lock",
        "regen_cmd": ["poetry", "lock", "--no-update"],
    },
    "pipenv": {
        "manifest": "Pipfile",
        "lockfile": "Pipfile.lock",
        "regen_cmd": ["pipenv", "lock"],
    },
    "uv": {
        "manifest": "pyproject.toml",
        "lockfile": "uv.lock",
        "regen_cmd": ["uv", "lock"],
    },
    "bundler": {
        "manifest": "Gemfile",
        "lockfile": "Gemfile.lock",
        "regen_cmd": ["bundle", "lock", "--update"],
    },
    "go": {
        "manifest": "go.mod",
        "lockfile": "go.sum",
        "regen_cmd": ["go", "mod", "tidy"],
    },
}


def resolve_lockfile(
    lockfile_path: str,
    strategy: str = "theirs",
    dry_run: bool = False,
) -> dict:
    """
    Resolve a conflicted lockfile by taking a side and regenerating.
    
    Args:
        lockfile_path: Path to the lockfile
        strategy: 'ours', 'theirs', or 'regen' (just regenerate)
        dry_run: If True, don't modify files
    
    Returns:
        dict with status and message
    """
    result = {
        "path": lockfile_path,
        "resolved": False,
        "message": "",
    }
    
    lockfile_type = detect_lockfile_type(lockfile_path)
    if not lockfile_type:
        result["message"] = "Unknown lockfile type"
        return result
    
    config = LOCKFILE_CONFIG.get(lockfile_type)
    if not config:
        result["message"] = f"No config for lockfile type: {lockfile_type}"
        return result
    
    # Check manifest exists
    manifest_path = Path(lockfile_path).parent / config["manifest"]
    if not manifest_path.exists():
        result["message"] = f"Manifest not found: {manifest_path}"
        return result
    
    if dry_run:
        result["resolved"] = True
        result["message"] = f"Would take {strategy} and regenerate with: {' '.join(config['regen_cmd'])}"
        return result
    
    # Take a side for the lockfile
    if strategy in ("ours", "theirs"):
        stage = ":2:" if strategy == "ours" else ":3:"
        git_result = run_git(["show", f"{stage}{lockfile_path}"])
        
        if git_result.returncode != 0:
            result["message"] = f"Could not extract {strategy} version"
            return result
        
        Path(lockfile_path).write_text(git_result.stdout)
    
    # Regenerate
    print(f"Regenerating {lockfile_path}...")
    regen_result = subprocess.run(
        config["regen_cmd"],
        capture_output=True,
        text=True,
        cwd=Path(lockfile_path).parent or ".",
    )
    
    if regen_result.returncode != 0:
        result["message"] = f"Regeneration failed: {regen_result.stderr}"
        return result
    
    # Stage the resolved lockfile
    run_git(["add", lockfile_path])
    
    result["resolved"] = True
    result["message"] = f"Took {strategy}, regenerated, and staged"
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Resolve lockfile conflicts by taking a side and regenerating"
    )
    parser.add_argument(
        "--strategy",
        choices=["ours", "theirs", "regen"],
        default="theirs",
        help="Strategy: take ours, theirs, or just regenerate (default: theirs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific lockfiles to resolve (default: auto-detect)",
    )
    
    args = parser.parse_args()
    
    # Get lockfiles to process
    if args.files:
        lockfiles = args.files
    else:
        # Auto-detect conflicted lockfiles
        all_conflicted = get_conflicted_files()
        lockfiles = [f for f in all_conflicted if detect_lockfile_type(f)]
    
    if not lockfiles:
        print("No conflicted lockfiles found.")
        return 0
    
    # Process each lockfile
    results = []
    for path in lockfiles:
        result = resolve_lockfile(path, args.strategy, args.dry_run)
        results.append(result)
        
        status = "✓" if result["resolved"] else "✗"
        print(f"{status} {result['path']}: {result['message']}")
    
    # Summary
    resolved = sum(1 for r in results if r["resolved"])
    print(f"\nResolved: {resolved}/{len(results)}")
    
    if args.dry_run and resolved > 0:
        print("Run without --dry-run to apply.")
    
    return 0 if resolved == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
