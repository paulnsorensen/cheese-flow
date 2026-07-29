"""Bounded repository discovery and canonicalization."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.models import RepositoryCandidate


def discover_repositories(
    roots: tuple[Path, ...], max_depth: int
) -> tuple[RepositoryCandidate, ...]:
    """Find repositories under ``roots``, never scanning outside them.

    Depth zero means the root itself. Candidates are canonicalized,
    deduplicated, resolved to their main worktree, and classified for name
    collisions and writability, in deterministic order.
    """
    raise NotImplementedError
