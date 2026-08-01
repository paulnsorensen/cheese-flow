"""Bounded repository discovery against a real filesystem."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from cheese_flow.models import CollisionClass, RepositoryCandidate
from cheese_flow.repositories import discover_repositories


def make_repo(path: Path) -> Path:
    """Create a plain checkout (a directory whose ``.git`` is a directory)."""
    (path / ".git").mkdir(parents=True)
    return path


def paths(candidates: tuple[RepositoryCandidate, ...]) -> list[Path]:
    return [candidate.canonical_path for candidate in candidates]


def by_path(candidates: tuple[RepositoryCandidate, ...], path: Path) -> RepositoryCandidate:
    match = [candidate for candidate in candidates if candidate.canonical_path == path]
    assert len(match) == 1, f"expected exactly one candidate at {path}, got {paths(candidates)}"
    return match[0]


def test_depth_zero_considers_only_the_root_itself(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "root")
    make_repo(root / "child")

    found = discover_repositories((root,), 0)

    assert paths(found) == [root]


def test_depth_zero_on_a_non_repository_root_finds_nothing(tmp_path: Path) -> None:
    root = tmp_path / "root"
    make_repo(root / "child")

    assert discover_repositories((root,), 0) == ()


def test_max_depth_bounds_descent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    shallow = make_repo(root / "shallow")
    deep = make_repo(root / "nested" / "deep")

    assert paths(discover_repositories((root,), 1)) == [shallow]
    assert paths(discover_repositories((root,), 2)) == [deep, shallow]


def test_discovery_does_not_descend_into_a_discovered_repository(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outer = make_repo(root / "outer")
    make_repo(outer / "inner")

    assert paths(discover_repositories((root,), 5)) == [outer]


def test_candidates_are_sorted_by_canonical_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    for name in ("charlie", "alpha", "bravo"):
        make_repo(root / name)

    found = discover_repositories((root,), 1)

    assert paths(found) == [root / "alpha", root / "bravo", root / "charlie"]


def test_repository_reachable_through_two_roots_appears_once(tmp_path: Path) -> None:
    root = tmp_path / "root"
    repo = make_repo(root / "nested" / "repo")

    found = discover_repositories((root, root / "nested"), 3)

    assert paths(found) == [repo]
    assert found[0].collision is CollisionClass.NONE


def test_symlinked_duplicate_is_canonicalized_to_one_candidate(tmp_path: Path) -> None:
    root = tmp_path / "root"
    repo = make_repo(root / "real")
    (root / "alias").symlink_to(repo, target_is_directory=True)

    found = discover_repositories((root,), 1)

    assert paths(found) == [repo]
    assert found[0].name == "real"


def test_symlink_pointing_outside_the_roots_is_not_a_candidate(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = make_repo(tmp_path / "outside" / "escapee")
    (root / "link").symlink_to(outside, target_is_directory=True)

    assert discover_repositories((root,), 2) == ()


def test_missing_root_is_skipped_and_other_roots_still_scan(tmp_path: Path) -> None:
    present = tmp_path / "present"
    repo = make_repo(present / "repo")

    found = discover_repositories((tmp_path / "does-not-exist", present), 1)

    assert paths(found) == [repo]


def test_root_that_is_a_file_is_skipped(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "roots.txt"
    not_a_directory.write_text("nope\n")

    assert discover_repositories((not_a_directory,), 2) == ()


def test_unreadable_directory_does_not_abort_the_scan(tmp_path: Path) -> None:
    root = tmp_path / "root"
    repo = make_repo(root / "repo")
    locked = root / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        found = discover_repositories((root,), 3)
    finally:
        locked.chmod(0o700)

    assert paths(found) == [repo]


def test_same_basename_at_different_paths_is_a_name_collision(tmp_path: Path) -> None:
    root = tmp_path / "root"
    first = make_repo(root / "a" / "proj")
    second = make_repo(root / "b" / "proj")
    lonely = make_repo(root / "c" / "solo")

    found = discover_repositories((root,), 2)

    assert by_path(found, first).collision is CollisionClass.NAME
    assert by_path(found, second).collision is CollisionClass.NAME
    assert by_path(found, lonely).collision is CollisionClass.NONE


def test_writability_reflects_filesystem_permission(tmp_path: Path) -> None:
    root = tmp_path / "root"
    writable = make_repo(root / "writable")
    read_only = make_repo(root / "read-only")
    read_only.chmod(0o500)
    try:
        found = discover_repositories((root,), 1)
    finally:
        read_only.chmod(0o700)

    assert by_path(found, writable).writable is True
    assert by_path(found, read_only).writable is False


def test_plain_checkout_is_its_own_main_worktree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "root" / "repo")

    found = discover_repositories((tmp_path / "root",), 1)

    assert by_path(found, repo).main_worktree == repo


def test_real_git_worktree_maps_back_to_its_main_worktree(tmp_path: Path) -> None:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git is unavailable")
    root = tmp_path / "root"
    main = root / "main"
    main.mkdir(parents=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True, env=env)
    (main / "file.txt").write_text("hi\n")
    subprocess.run(["git", "-C", str(main), "add", "file.txt"], check=True, env=env)
    subprocess.run(["git", "-C", str(main), "commit", "-qm", "init"], check=True, env=env)
    linked = root / "linked"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", str(linked), "-b", "side"],
        check=True,
        env=env,
    )

    found = discover_repositories((root,), 1)

    assert paths(found) == [linked, main]
    assert by_path(found, linked).main_worktree == main
    assert by_path(found, main).main_worktree == main
    assert by_path(found, linked).collision is CollisionClass.WORKTREE
    assert by_path(found, main).collision is CollisionClass.WORKTREE


def test_gitdir_file_with_relative_path_resolves_the_main_worktree(tmp_path: Path) -> None:
    root = tmp_path / "root"
    main = make_repo(root / "main")
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
    linked = root / "wt"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: ../main/.git/worktrees/wt\n")

    found = discover_repositories((root,), 1)

    assert by_path(found, linked).main_worktree == main
    assert by_path(found, main).main_worktree == main


def test_worktree_collision_wins_over_name_collision(tmp_path: Path) -> None:
    root = tmp_path / "root"
    main = make_repo(root / "a" / "proj")
    (main / ".git" / "worktrees" / "proj").mkdir(parents=True)
    linked = root / "b" / "proj"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'proj'}\n")

    found = discover_repositories((root,), 2)

    assert by_path(found, main).collision is CollisionClass.WORKTREE
    assert by_path(found, linked).collision is CollisionClass.WORKTREE


def test_unparseable_gitdir_file_falls_back_to_the_repository_itself(tmp_path: Path) -> None:
    root = tmp_path / "root"
    broken = root / "broken"
    broken.mkdir(parents=True)
    (broken / ".git").write_text("not a gitdir pointer\n")

    found = discover_repositories((root,), 1)

    assert paths(found) == [broken]
    assert found[0].main_worktree == broken
    assert found[0].collision is CollisionClass.NONE


def test_candidates_carry_no_selection_state(tmp_path: Path) -> None:
    make_repo(tmp_path / "root" / "repo")

    found = discover_repositories((tmp_path / "root",), 1)

    assert "selected" not in found[0].model_fields_set
    assert not hasattr(found[0], "selected")


def test_no_roots_yields_no_candidates() -> None:
    assert discover_repositories((), 3) == ()
