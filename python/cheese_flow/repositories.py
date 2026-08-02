"""Bounded repository discovery and canonicalization."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from cheese_flow.models import CollisionClass, RepositoryCandidate

_GITDIR_PREFIX = "gitdir:"


def discover_repositories(
    roots: tuple[Path, ...], max_depth: int
) -> tuple[RepositoryCandidate, ...]:
    """Find repositories under ``roots``, never scanning outside them.

    Depth zero means the root itself. Candidates are canonicalized,
    deduplicated, resolved to their main worktree, and classified for name
    collisions and writability, in deterministic order.
    """
    boundaries = _canonical_roots(roots)
    found: dict[Path, Path] = {}
    for root in boundaries:
        for repo in _scan(root, max_depth, boundaries):
            found.setdefault(repo, _main_worktree(repo))

    name_counts = Counter(repo.name for repo in found)
    worktree_counts = Counter(found.values())
    return tuple(
        RepositoryCandidate(
            canonical_path=repo,
            name=repo.name,
            main_worktree=main,
            writable=os.access(repo, os.W_OK | os.X_OK),
            collision=_classify(repo, main, name_counts, worktree_counts),
        )
        for repo, main in sorted(found.items())
    )


def _classify(
    repo: Path,
    main: Path,
    name_counts: Counter[str],
    worktree_counts: Counter[Path],
) -> CollisionClass:
    if worktree_counts[main] > 1:
        return CollisionClass.WORKTREE
    if name_counts[repo.name] > 1:
        return CollisionClass.NAME
    return CollisionClass.NONE


def _canonical_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    canonical: list[Path] = []
    for root in roots:
        resolved = _resolve(root)
        if resolved is not None and resolved.is_dir() and resolved not in canonical:
            canonical.append(resolved)
    return tuple(canonical)


def _scan(root: Path, max_depth: int, boundaries: tuple[Path, ...]) -> list[Path]:
    """Breadth-first walk of ``root`` down to ``max_depth``, pruning at repositories."""
    repos: list[Path] = []
    level = [root]
    for depth in range(max_depth + 1):
        if not level:
            break
        next_level: list[Path] = []
        for directory in level:
            canonical = _resolve(directory)
            if canonical is None or not _within(canonical, boundaries):
                continue
            if is_repository(canonical):
                repos.append(canonical)
                continue
            if depth < max_depth:
                next_level.extend(_child_directories(directory))
        level = next_level
    return repos


def _child_directories(directory: Path) -> list[Path]:
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return []
    children: list[Path] = []
    for entry in entries:
        try:
            if entry.is_dir():
                children.append(Path(entry.path))
        except OSError:
            continue
    return children


def is_repository(directory: Path) -> bool:
    """Whether ``directory`` is a git repository — a checkout or a linked worktree."""
    try:
        return (directory / ".git").exists()
    except OSError:
        return False


def _within(path: Path, boundaries: tuple[Path, ...]) -> bool:
    return any(path == boundary or boundary in path.parents for boundary in boundaries)


def _resolve(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _main_worktree(repo: Path) -> Path:
    """Map a linked worktree back to its main worktree; plain checkouts map to themselves."""
    dot_git = repo / ".git"
    if dot_git.is_dir():
        return repo
    gitdir = _read_gitdir(repo, dot_git)
    if gitdir is None:
        return repo
    common = _common_git_dir(gitdir)
    if common is not None and common.name == ".git" and common.parent.is_dir():
        return common.parent
    return repo


def _read_gitdir(repo: Path, dot_git: Path) -> Path | None:
    try:
        pointer = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not pointer.startswith(_GITDIR_PREFIX):
        return None
    target = Path(pointer[len(_GITDIR_PREFIX) :].strip())
    if not str(target).strip():
        return None
    return _resolve(target if target.is_absolute() else repo / target)


def _common_git_dir(gitdir: Path) -> Path | None:
    commondir = gitdir / "commondir"
    if commondir.is_file():
        try:
            relative = commondir.read_text(encoding="utf-8").strip()
        except OSError:
            relative = ""
        if relative:
            return _resolve(Path(relative) if Path(relative).is_absolute() else gitdir / relative)
    return next((parent for parent in gitdir.parents if parent.name == ".git"), None)
