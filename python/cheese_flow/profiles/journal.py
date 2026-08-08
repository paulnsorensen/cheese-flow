"""Private, durable journal primitives for profile apply recovery."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .errors import ProfileApplyError

_GENERATION_RE = re.compile(r"[0-9a-f]{64}")
_JOURNAL_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_path",
        "manifest_sha256",
        "generation",
        "previous_managed",
        "desired_managed",
        "phase",
    }
)

JournalPhase: TypeAlias = Literal["prepared", "files_written", "stale_deleted"]
RecoveryAction: TypeAlias = Literal["write_files", "delete_stale", "commit_state"]

_NEXT_PHASE: dict[JournalPhase, JournalPhase] = {
    "prepared": "files_written",
    "files_written": "stale_deleted",
}
_RECOVERY_ACTIONS: dict[JournalPhase, RecoveryAction] = {
    "prepared": "write_files",
    "files_written": "delete_stale",
    "stale_deleted": "commit_state",
}


class ProfileApplyJournal(BaseModel):
    """Private v1 recovery record for one immutable profile generation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    manifest_path: Path
    manifest_sha256: str
    generation: str
    previous_managed: tuple[Path, ...]
    desired_managed: tuple[Path, ...]
    phase: JournalPhase

    @field_validator("manifest_path")
    @classmethod
    def _manifest_path_is_canonical_absolute(cls, value: Path) -> Path:
        return _validate_canonical_path(value, "journal manifest_path")

    @field_validator("manifest_sha256", "generation")
    @classmethod
    def _digest_is_lowercase_sha256(cls, value: str, info) -> str:
        if _GENERATION_RE.fullmatch(value) is None:
            raise ValueError(
                f"journal {info.field_name} must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("previous_managed", "desired_managed")
    @classmethod
    def _managed_paths_are_canonical_sorted_unique(
        cls, value: tuple[Path, ...], info
    ) -> tuple[Path, ...]:
        paths = tuple(
            _validate_canonical_path(path, f"journal {info.field_name} path") for path in value
        )
        if len(paths) != len(set(paths)):
            raise ValueError(f"journal {info.field_name} must not contain duplicate paths")
        ordered = tuple(sorted(paths, key=lambda path: path.as_posix()))
        if paths != ordered:
            raise ValueError(f"journal {info.field_name} must be sorted")
        return paths


def _validate_canonical_path(value: Path, label: str) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"{label} must be a path")
    if not value.is_absolute():
        raise ValueError(f"{label} must be absolute")
    try:
        canonical = value.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"{label} is not usable: {value}") from exc
    if canonical != value:
        raise ValueError(f"{label} must be canonical: {value}")
    return value


def _error(message: str, cause: BaseException | None = None) -> ProfileApplyError:
    error = ProfileApplyError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _journal_path(path: Path) -> Path:
    try:
        return Path(path)
    except (TypeError, ValueError) as exc:
        raise _error(f"profile apply journal path is invalid: {path!r}", exc) from exc


def _absolute_manifest_path(path: Path) -> Path:
    raw_path = Path(path)
    try:
        return raw_path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _error(f"profile apply manifest path is not usable: {raw_path}", exc) from exc


def _canonical_managed_paths(values: Iterable[Path], field_name: str) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes)):
        raise _error(f"journal {field_name} must be a sequence of paths")
    try:
        raw_paths = tuple(Path(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise _error(f"journal {field_name} must be a sequence of paths", exc) from exc

    canonical: list[Path] = []
    for path in raw_paths:
        canonical.append(_absolute_manifest_path(path))
    if len(canonical) != len(set(canonical)):
        raise _error(f"journal {field_name} must not contain duplicate paths")
    return tuple(sorted(canonical, key=lambda path: path.as_posix()))


def _validated_journal(value: ProfileApplyJournal | object) -> ProfileApplyJournal:
    if isinstance(value, ProfileApplyJournal):
        return value
    try:
        return ProfileApplyJournal.model_validate(value)
    except (TypeError, ValueError, ValidationError) as exc:
        raise _error("profile apply journal is malformed", exc) from exc


def _decode_journal(payload: object) -> ProfileApplyJournal:
    if not isinstance(payload, dict):
        raise _error("profile apply journal must contain a JSON object")
    keys = set(payload)
    if keys != _JOURNAL_FIELDS:
        missing = sorted(_JOURNAL_FIELDS - keys)
        extra = sorted(keys - _JOURNAL_FIELDS)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        raise _error(f"profile apply journal has unexpected fields ({'; '.join(details)})")

    if isinstance(payload["schema_version"], bool) or payload["schema_version"] != 1:
        raise _error("profile apply journal has unsupported schema_version")
    for field in ("manifest_path", "manifest_sha256", "generation", "phase"):
        if not isinstance(payload[field], str):
            raise _error(f"profile apply journal field {field!r} is malformed")
    for field in ("previous_managed", "desired_managed"):
        values = payload[field]
        if not isinstance(values, list) or not all(isinstance(path, str) for path in values):
            raise _error(f"profile apply journal field {field!r} is malformed")

    return _validated_journal(payload)


def _encode_journal(journal: ProfileApplyJournal) -> bytes:
    payload = {
        "schema_version": journal.schema_version,
        "manifest_path": str(journal.manifest_path),
        "manifest_sha256": journal.manifest_sha256,
        "generation": journal.generation,
        "previous_managed": [str(path) for path in journal.previous_managed],
        "desired_managed": [str(path) for path in journal.desired_managed],
        "phase": journal.phase,
    }
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise _error(f"could not open journal directory for durability: {directory}", exc) from exc
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise _error(f"could not durably update journal directory: {directory}", exc) from exc
    finally:
        os.close(directory_fd)


def _write_journal(path: Path, journal: ProfileApplyJournal) -> None:
    path = _journal_path(path)
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _error(f"could not create profile apply journal directory: {parent}", exc) from exc

    temporary: str | None = None
    handle: int | None = None
    try:
        handle, temporary = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "wb") as stream:
            handle = None
            stream.write(_encode_journal(journal))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    except ProfileApplyError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise _error(f"could not durably write profile apply journal: {path}", exc) from exc
    finally:
        if handle is not None:
            with contextlib.suppress(OSError):
                os.close(handle)
        if temporary is not None:
            with contextlib.suppress(OSError):
                Path(temporary).unlink(missing_ok=True)


def load_journal(path: Path) -> ProfileApplyJournal | None:
    """Load one exact journal, returning ``None`` when it is absent."""

    journal_path = _journal_path(path)
    try:
        if journal_path.is_symlink():
            raise _error(f"profile apply journal must not be a symlink: {journal_path}")
        if not journal_path.exists():
            return None
        if not journal_path.is_file():
            raise _error(f"profile apply journal is not a regular file: {journal_path}")
        raw = journal_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except ProfileApplyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error(f"profile apply journal is unreadable: {journal_path}", exc) from exc
    return _decode_journal(payload)


def prepare_journal(
    path: Path,
    *,
    generation: str,
    manifest_path: Path,
    manifest_sha256: str,
    previous_managed: Iterable[Path],
    desired_managed: Iterable[Path],
) -> ProfileApplyJournal:
    """Persist a fresh prepared journal for one immutable generation."""

    try:
        journal = ProfileApplyJournal(
            manifest_path=_absolute_manifest_path(manifest_path),
            manifest_sha256=manifest_sha256,
            generation=generation,
            previous_managed=_canonical_managed_paths(previous_managed, "previous_managed"),
            desired_managed=_canonical_managed_paths(desired_managed, "desired_managed"),
            phase="prepared",
        )
    except ProfileApplyError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise _error("profile apply journal is malformed", exc) from exc
    _write_journal(path, journal)
    return journal


def advance_journal(
    path: Path, journal: ProfileApplyJournal, phase: JournalPhase
) -> ProfileApplyJournal:
    """Persist exactly the next journal phase after checking the on-disk record."""

    current = _validated_journal(journal)
    journal_path = _journal_path(path)
    on_disk = load_journal(journal_path)
    if on_disk is None:
        raise _error(f"profile apply journal is missing: {journal_path}")
    if on_disk != current:
        raise _error(f"profile apply journal changed unexpectedly: {journal_path}")

    next_phase = _NEXT_PHASE.get(current.phase)
    if next_phase is None or phase != next_phase:
        raise _error(f"invalid profile apply journal transition: {current.phase!r} -> {phase!r}")
    try:
        advanced = current.model_copy(update={"phase": phase})
    except (TypeError, ValueError, ValidationError) as exc:
        raise _error("profile apply journal transition is malformed", exc) from exc
    _write_journal(journal_path, advanced)
    return advanced


def remove_journal(path: Path) -> None:
    """Remove a journal after state commit; repeated removal is harmless."""

    journal_path = _journal_path(path)
    try:
        if journal_path.is_symlink():
            raise _error(f"profile apply journal must not be a symlink: {journal_path}")
        if not journal_path.exists():
            return
        if not journal_path.is_file():
            raise _error(f"profile apply journal is not a regular file: {journal_path}")
        journal_path.unlink()
        _fsync_directory(journal_path.parent)
    except ProfileApplyError:
        raise
    except OSError as exc:
        raise _error(f"could not remove profile apply journal: {journal_path}", exc) from exc


def recovery_action(journal: ProfileApplyJournal) -> RecoveryAction:
    """Return the deterministic idempotent action for a journal phase."""

    current = _validated_journal(journal)
    return _RECOVERY_ACTIONS[current.phase]


__all__ = [
    "JournalPhase",
    "ProfileApplyJournal",
    "RecoveryAction",
    "advance_journal",
    "load_journal",
    "prepare_journal",
    "recovery_action",
    "remove_journal",
]
