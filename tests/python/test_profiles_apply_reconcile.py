"""Behavioral tests for atomic profile apply reconciliation."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfileApplyError
from cheese_flow.profiles.preflight import PlannedReplacement, PreflightPlan
from cheese_flow.profiles.reconcile import delete_stale, write_replacements

_GENERATION = "a" * 64


def _replacement(
    root: Path,
    relative: str,
    content: bytes,
    *,
    mode: int = 0o600,
) -> PlannedReplacement:
    return PlannedReplacement(
        target_root=root,
        destination=root / relative,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        mode=mode,
    )


def _plan(
    root: Path,
    *,
    replacements: tuple[PlannedReplacement, ...] = (),
    stale_files: tuple[Path, ...] = (),
) -> PreflightPlan:
    return PreflightPlan(
        generation=_GENERATION,
        target_roots=(root,),
        replacements=replacements,
        stale_files=stale_files,
        managed_files=tuple(item.destination for item in replacements),
    )


def test_write_replacements_atomically_replaces_nested_files(tmp_path: Path) -> None:
    root = tmp_path / "target"
    root.mkdir()
    destination = root / ".config" / "cheese" / "profile.json"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old")
    plan = _plan(root, replacements=(_replacement(root, ".config/cheese/profile.json", b"new"),))

    assert write_replacements(plan) == (destination,)
    assert destination.read_bytes() == b"new"
    assert tuple(destination.parent.glob(f".{destination.name}.*.tmp")) == ()


def test_write_replacements_applies_executable_mode_atomically(tmp_path: Path) -> None:
    root = tmp_path / "target"
    root.mkdir()
    destination = root / "hook"
    plan = _plan(
        root,
        replacements=(_replacement(root, "hook", b"#!/bin/sh\n", mode=0o755),),
    )

    assert write_replacements(plan) == (destination,)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o755


def test_write_replacements_preserves_destination_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "target"
    root.mkdir()
    destination = root / "profile.json"
    destination.write_bytes(b"old")
    plan = _plan(root, replacements=(_replacement(root, "profile.json", b"new"),))

    def fail_replace(_temporary: str | Path, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("cheese_flow.profiles.reconcile.os.replace", fail_replace)

    with pytest.raises(ProfileApplyError, match="profile.json"):
        write_replacements(plan)

    assert destination.read_bytes() == b"old"
    assert tuple(root.glob(f".{destination.name}.*.tmp")) == ()


def test_delete_stale_removes_only_prior_owned_paths_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "target"
    root.mkdir()
    stale = root / "old.json"
    user_owned = root / "notes.txt"
    stale.write_bytes(b"stale")
    user_owned.write_bytes(b"keep")
    plan = _plan(root, stale_files=(stale,))

    assert delete_stale(plan) == (stale,)
    assert not stale.exists()
    assert user_owned.read_bytes() == b"keep"
    assert delete_stale(plan) == (stale,)
    assert user_owned.read_bytes() == b"keep"


def test_reconciliation_rejects_stale_path_without_target_ownership(tmp_path: Path) -> None:
    root = tmp_path / "target"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"keep")
    plan = _plan(root, stale_files=(outside,))

    with pytest.raises(ProfileApplyError, match="no containing target root"):
        delete_stale(plan)

    assert outside.read_bytes() == b"keep"


def test_reconciliation_rejects_symlink_boundaries_before_mutation(tmp_path: Path) -> None:
    root = tmp_path / "target"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "nested").symlink_to(outside, target_is_directory=True)
    root / "nested" / "profile.json"
    plan = _plan(root, replacements=(_replacement(root, "nested/profile.json", b"content"),))

    with pytest.raises(ProfileApplyError, match="replace"):
        write_replacements(plan)

    assert not (outside / "profile.json").exists()
