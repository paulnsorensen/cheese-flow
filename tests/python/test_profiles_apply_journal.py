"""Behavioral tests for private profile-apply journal transitions."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfileApplyError
from cheese_flow.profiles.journal import (
    ProfileApplyJournal,
    advance_journal,
    load_journal,
    prepare_journal,
    recovery_action,
    remove_journal,
)

_GENERATION = "a" * 64
_MANIFEST_SHA256 = "b" * 64


def _prepare(
    journal_path: Path,
    *,
    manifest_path: Path,
    previous_managed: tuple[Path, ...] = (),
    desired_managed: tuple[Path, ...] = (),
) -> ProfileApplyJournal:
    return prepare_journal(
        journal_path,
        generation=_GENERATION,
        manifest_path=manifest_path,
        manifest_sha256=_MANIFEST_SHA256,
        previous_managed=previous_managed,
        desired_managed=desired_managed,
    )


def test_prepare_persists_absolute_compact_private_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "state" / "apply.journal"
    manifest_path = tmp_path / "compiled" / "manifest.json"
    previous = (tmp_path / "target" / "z.json", tmp_path / "target" / "a.json")
    desired = (tmp_path / "target" / "new.json",)

    journal = _prepare(
        journal_path,
        manifest_path=manifest_path,
        previous_managed=previous,
        desired_managed=desired,
    )

    assert journal == ProfileApplyJournal(
        schema_version=1,
        manifest_path=manifest_path.resolve(),
        manifest_sha256=_MANIFEST_SHA256,
        generation=_GENERATION,
        previous_managed=tuple(
            sorted((path.resolve() for path in previous), key=lambda p: p.as_posix())
        ),
        desired_managed=(desired[0].resolve(),),
        phase="prepared",
    )
    assert load_journal(journal_path) == journal
    assert stat.S_IMODE(journal_path.stat().st_mode) == 0o600
    raw = journal_path.read_text()
    assert ": " not in raw
    assert ", " not in raw
    assert json.loads(raw) == {
        "desired_managed": [str(desired[0].resolve())],
        "generation": _GENERATION,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _MANIFEST_SHA256,
        "phase": "prepared",
        "previous_managed": [
            str(path.resolve()) for path in sorted(previous, key=lambda p: p.as_posix())
        ],
        "schema_version": 1,
    }


def test_recovery_action_and_exact_phase_transitions_are_deterministic(tmp_path: Path) -> None:
    journal_path = tmp_path / "apply.journal"
    journal = _prepare(journal_path, manifest_path=tmp_path / "manifest.json")

    assert recovery_action(journal) == "write_files"
    journal = advance_journal(journal_path, journal, "files_written")
    assert recovery_action(journal) == "delete_stale"
    journal = advance_journal(journal_path, journal, "stale_deleted")
    assert recovery_action(journal) == "commit_state"
    assert load_journal(journal_path) == journal


def test_invalid_transition_keeps_current_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "apply.journal"
    journal = _prepare(journal_path, manifest_path=tmp_path / "manifest.json")
    before = journal_path.read_bytes()

    with pytest.raises(ProfileApplyError, match="invalid .* transition"):
        advance_journal(journal_path, journal, "stale_deleted")

    assert journal_path.read_bytes() == before
    assert load_journal(journal_path) == journal


def test_stale_transition_cannot_overwrite_an_advanced_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "apply.journal"
    prepared = _prepare(journal_path, manifest_path=tmp_path / "manifest.json")
    advance_journal(journal_path, prepared, "files_written")

    with pytest.raises(ProfileApplyError, match="changed unexpectedly"):
        advance_journal(journal_path, prepared, "files_written")

    assert load_journal(journal_path).phase == "files_written"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": 1,
            "manifest_path": "/tmp/manifest.json",
            "manifest_sha256": _MANIFEST_SHA256,
            "generation": _GENERATION,
            "previous_managed": [],
            "desired_managed": [],
        },
        {
            "schema_version": 1,
            "manifest_path": "/tmp/manifest.json",
            "manifest_sha256": _MANIFEST_SHA256,
            "generation": _GENERATION,
            "previous_managed": [],
            "desired_managed": [],
            "phase": "unknown",
        },
        {
            "schema_version": 1,
            "manifest_path": "relative/manifest.json",
            "manifest_sha256": _MANIFEST_SHA256,
            "generation": _GENERATION,
            "previous_managed": [],
            "desired_managed": [],
            "phase": "prepared",
        },
        {
            "schema_version": 1,
            "manifest_path": "/tmp/manifest.json",
            "manifest_sha256": _MANIFEST_SHA256,
            "generation": _GENERATION,
            "previous_managed": ["/tmp/z", "/tmp/a"],
            "desired_managed": [],
            "phase": "prepared",
        },
        {
            "schema_version": 1,
            "manifest_path": "/tmp/manifest.json",
            "manifest_sha256": _MANIFEST_SHA256,
            "generation": _GENERATION,
            "previous_managed": [],
            "desired_managed": [],
            "phase": "prepared",
            "unexpected": True,
        },
    ],
)
def test_malformed_journal_fails_closed_without_removing_it(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    journal_path = tmp_path / "apply.journal"
    journal_path.write_text(json.dumps(payload))

    with pytest.raises(ProfileApplyError, match="journal"):
        load_journal(journal_path)

    assert journal_path.exists()


def test_prepare_rejects_duplicate_managed_paths(tmp_path: Path) -> None:
    duplicate = tmp_path / "target" / "profile.json"

    with pytest.raises(ProfileApplyError, match="duplicate"):
        _prepare(
            tmp_path / "apply.journal",
            manifest_path=tmp_path / "manifest.json",
            previous_managed=(duplicate, duplicate),
        )


def test_remove_journal_is_idempotent(tmp_path: Path) -> None:
    journal_path = tmp_path / "apply.journal"
    _prepare(journal_path, manifest_path=tmp_path / "manifest.json")

    remove_journal(journal_path)
    remove_journal(journal_path)

    assert not journal_path.exists()


def test_missing_journal_is_distinct_from_malformed_journal(tmp_path: Path) -> None:
    assert load_journal(tmp_path / "missing.journal") is None


def test_prepare_rejects_invalid_digests(tmp_path: Path) -> None:
    with pytest.raises(ProfileApplyError, match="journal"):
        prepare_journal(
            tmp_path / "apply.journal",
            generation="not-a-generation",
            manifest_path=tmp_path / "manifest.json",
            manifest_sha256=_MANIFEST_SHA256,
            previous_managed=(),
            desired_managed=(),
        )
    with pytest.raises(ProfileApplyError, match="journal"):
        prepare_journal(
            tmp_path / "apply.journal",
            generation=_GENERATION,
            manifest_path=tmp_path / "manifest.json",
            manifest_sha256="not-a-digest",
            previous_managed=(),
            desired_managed=(),
        )
