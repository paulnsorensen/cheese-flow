"""Journaled application and recovery for compiled profile generations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from .errors import ProfileApplyError
from .journal import (
    advance_journal,
    load_journal,
    prepare_journal,
    recovery_action,
    remove_journal,
)
from .models import ProfileApplyReport, ProfileApplyState
from .preflight import PreflightPlan, _validate_control_path, preflight_apply
from .reconcile import delete_stale, write_replacements

DEFAULT_STATE_FILENAME = "apply-state.json"

_STATE_FIELDS = frozenset({"schema_version", "managed_files"})
_LEGACY_STATE_FIELDS = frozenset({"managed_files"})


def _error(message: str, cause: BaseException | None = None) -> ProfileApplyError:
    error = ProfileApplyError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _diagnose_cleanup_failure(
    active_exception: BaseException | None,
    message: str,
    cleanup_error: BaseException,
) -> None:
    if active_exception is None:
        raise _error(message, cleanup_error) from cleanup_error
    active_exception.add_note(f"{message}: {cleanup_error}")


def _state_path(manifest_path: Path, state_path: Path | None) -> Path:
    return (
        Path(manifest_path).parent / DEFAULT_STATE_FILENAME
        if state_path is None
        else Path(state_path)
    )


def _journal_path(state_path: Path) -> Path:
    return Path(f"{Path(state_path)}.journal")


def _lock_path(state_path: Path) -> Path:
    return Path(f"{Path(state_path)}.lock")


def _control_paths(state_path: Path) -> dict[str, Path]:
    return {
        "state": Path(state_path),
        "journal": _journal_path(state_path),
        "lock": _lock_path(state_path),
    }


def _validate_apply_controls(control_paths: dict[str, Path]) -> None:
    for label, path in control_paths.items():
        _validate_control_path(
            path,
            kind=f"profile apply {label}",
            require_regular_file=True,
        )


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise _error(f"could not open apply directory for durability: {directory}", exc) from exc
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise _error(f"could not durably update apply directory: {directory}", exc) from exc
    finally:
        os.close(directory_fd)


@contextmanager
def _exclusive_lock(path: Path) -> Generator[None]:
    """Serialize applies sharing one state path."""

    lock_path = Path(path)
    descriptor: int | None = None
    try:
        _validate_control_path(
            lock_path,
            kind="profile apply lock",
            require_regular_file=True,
        )
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            _validate_control_path(
                lock_path,
                kind="profile apply lock",
                require_regular_file=True,
            )
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError as exc:
            raise _error(f"could not acquire profile apply lock: {lock_path}", exc) from exc

        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                raise _error(f"could not release profile apply lock: {lock_path}", exc) from exc
            finally:
                os.close(descriptor)
                descriptor = None
    except ProfileApplyError:
        raise
    except OSError as exc:
        raise _error(f"could not close profile apply lock: {lock_path}", exc) from exc
    finally:
        if descriptor is not None:
            active_exception = sys.exc_info()[1]
            try:
                os.close(descriptor)
            except BaseException as cleanup_error:
                _diagnose_cleanup_failure(
                    active_exception,
                    f"could not close profile apply lock: {lock_path}",
                    cleanup_error,
                )


def _read_state(state_path: Path) -> ProfileApplyState | None:
    """Read either exact legacy state or schema-v1 state without changing it."""

    path = Path(state_path)
    try:
        if path.is_symlink():
            raise _error(f"profile apply state must not be a symlink: {path}")
        if not path.exists():
            return None
        if not path.is_file():
            raise _error(f"profile apply state is not a regular file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ProfileApplyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error(f"profile apply state is unreadable: {path}", exc) from exc

    if not isinstance(payload, dict):
        raise _error(f"profile apply state must contain a JSON object: {path}")
    keys = set(payload)
    if keys == _LEGACY_STATE_FIELDS:
        pass
    elif keys == _STATE_FIELDS:
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, bool) or schema_version != 1:
            raise _error(f"profile apply state has unsupported schema_version: {path}")
    else:
        raise _error(f"profile apply state has unexpected fields: {path}")

    managed = payload.get("managed_files")
    if not isinstance(managed, list) or not all(isinstance(value, str) for value in managed):
        raise _error(f"profile apply state managed_files is malformed: {path}")

    lexical: list[Path] = []
    seen: set[Path] = set()
    for value in managed:
        candidate = Path(value)
        if not candidate.is_absolute():
            raise _error(f"profile apply state path must be absolute: {candidate}")
        if candidate in seen:
            raise _error(f"profile apply state contains duplicate managed paths: {path}")
        seen.add(candidate)
        lexical.append(candidate)

    try:
        return ProfileApplyState(schema_version=1, managed_files=tuple(lexical))
    except (TypeError, ValueError, ValidationError) as exc:
        raise _error(f"profile apply state is malformed: {path}", exc) from exc


def _write_state(state_path: Path, state: ProfileApplyState) -> None:
    """Atomically persist schema-v1 ownership state after journal completion."""

    path = Path(state_path)
    _validate_control_path(
        path,
        kind="profile apply state",
        require_regular_file=True,
    )
    try:
        state = (
            state
            if isinstance(state, ProfileApplyState)
            else ProfileApplyState.model_validate(state)
        )
        payload = {
            "schema_version": 1,
            "managed_files": [str(item) for item in state.managed_files],
        }
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        _validate_control_path(
            path,
            kind="profile apply state",
            require_regular_file=True,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _validate_control_path(
            path,
            kind="profile apply state",
            require_regular_file=True,
        )
    except ProfileApplyError:
        raise
    except (OSError, TypeError, ValueError, ValidationError) as exc:
        raise _error(f"could not prepare profile apply state: {path}", exc) from exc

    temporary: str | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_control_path(
            path,
            kind="profile apply state",
            require_regular_file=True,
        )
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    except ProfileApplyError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise _error(f"could not durably write profile apply state: {path}", exc) from exc
    finally:
        active_exception = sys.exc_info()[1]
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as cleanup_error:
                _diagnose_cleanup_failure(
                    active_exception,
                    f"could not close temporary profile apply state: {path}",
                    cleanup_error,
                )
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except BaseException as cleanup_error:
                _diagnose_cleanup_failure(
                    active_exception,
                    f"could not clean temporary profile apply state: {temporary}",
                    cleanup_error,
                )


def _immutable_manifest_path(manifest_path: Path, generation: str) -> Path:
    path = Path(manifest_path)
    generation_root = path.parent
    if generation_root.name == generation and generation_root.parent.name == "generations":
        return path
    return generation_root / "generations" / generation / "manifest.json"


def _manifest_identity(manifest_path: Path) -> tuple[Path, str]:
    raw_path = Path(manifest_path)
    try:
        resolved = _validate_control_path(
            raw_path,
            kind="profile manifest",
            require_regular_file=True,
        ).resolve(strict=True)
        if not resolved.is_file():
            raise _error(f"profile manifest is not a regular file: {raw_path}")
        content = resolved.read_bytes()
    except ProfileApplyError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise _error(f"profile manifest is not usable: {raw_path}", exc) from exc
    return resolved, hashlib.sha256(content).hexdigest()


def _plan_for_journal(
    journal_path: Path,
    journal,
    *,
    reserved_paths: dict[str, Path] | None = None,
) -> PreflightPlan:
    manifest_path, manifest_sha256 = _manifest_identity(journal.manifest_path)
    if manifest_path != journal.manifest_path:
        raise _error(
            f"profile apply journal manifest path is not canonical: {journal.manifest_path}"
        )
    if manifest_sha256 != journal.manifest_sha256:
        raise _error(f"profile apply journal manifest hash mismatch: {manifest_path}")

    previous = ProfileApplyState(schema_version=1, managed_files=journal.previous_managed)
    try:
        plan = preflight_apply(
            manifest_path,
            previous,
            reserved_paths=reserved_paths,
        )
    except ProfileApplyError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
        raise _error(f"could not recover profile apply journal: {journal_path}", exc) from exc
    if plan.generation != journal.generation:
        raise _error(f"profile apply journal generation mismatch: {manifest_path}")
    if plan.managed_files != journal.desired_managed:
        raise _error(f"profile apply journal ownership mismatch: {manifest_path}")
    return plan


def _commit_recovered_state(state_path: Path, journal_path: Path, plan: PreflightPlan) -> None:
    state = ProfileApplyState(schema_version=1, managed_files=plan.managed_files)
    _write_state(state_path, state)
    _validate_control_path(
        journal_path,
        kind="profile apply journal",
        require_regular_file=True,
    )
    remove_journal(journal_path)


def _recover_pending(state_path: Path) -> None:
    journal_path = _journal_path(state_path)
    _validate_control_path(
        journal_path,
        kind="profile apply journal",
        require_regular_file=True,
    )
    journal = load_journal(journal_path)
    if journal is None:
        return

    control_paths = _control_paths(state_path)
    _validate_apply_controls(control_paths)
    plan = _plan_for_journal(
        journal_path,
        journal,
        reserved_paths=control_paths,
    )
    action = recovery_action(journal)
    if action == "write_files":
        write_replacements(plan)
        _validate_control_path(
            journal_path,
            kind="profile apply journal",
            require_regular_file=True,
        )
        journal = advance_journal(journal_path, journal, "files_written")
        action = recovery_action(journal)
    if action == "delete_stale":
        delete_stale(plan)
        _validate_control_path(
            journal_path,
            kind="profile apply journal",
            require_regular_file=True,
        )
        journal = advance_journal(journal_path, journal, "stale_deleted")
        action = recovery_action(journal)
    if action == "commit_state":
        _commit_recovered_state(state_path, journal_path, plan)


def _apply_manifest(manifest_path: Path, state_path: Path) -> ProfileApplyReport:
    prior = _read_state(state_path)
    requested_manifest, _ = _manifest_identity(manifest_path)
    control_paths = _control_paths(state_path)
    try:
        requested_plan = preflight_apply(
            requested_manifest,
            prior,
            reserved_paths=control_paths,
        )
    except ProfileApplyError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
        raise _error(f"could not preflight profile apply: {requested_manifest}", exc) from exc

    immutable_manifest = _immutable_manifest_path(requested_manifest, requested_plan.generation)
    manifest_file, manifest_sha256 = _manifest_identity(immutable_manifest)
    if manifest_file == requested_manifest:
        plan = requested_plan
    else:
        try:
            plan = preflight_apply(
                manifest_file,
                prior,
                reserved_paths=control_paths,
            )
        except ProfileApplyError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
            raise _error(
                f"could not preflight immutable profile manifest: {manifest_file}",
                exc,
            ) from exc
        if plan.generation != requested_plan.generation:
            raise _error(f"profile manifest generation changed: {requested_manifest}")

    previous_managed = () if prior is None else prior.managed_files
    journal_path = _journal_path(state_path)
    _validate_apply_controls(control_paths)
    journal = prepare_journal(
        journal_path,
        generation=plan.generation,
        manifest_path=manifest_file,
        manifest_sha256=manifest_sha256,
        previous_managed=previous_managed,
        desired_managed=plan.managed_files,
    )

    copied = write_replacements(plan)
    _validate_control_path(
        journal_path,
        kind="profile apply journal",
        require_regular_file=True,
    )
    journal = advance_journal(journal_path, journal, "files_written")
    deleted = delete_stale(plan)
    _validate_control_path(
        journal_path,
        kind="profile apply journal",
        require_regular_file=True,
    )
    journal = advance_journal(journal_path, journal, "stale_deleted")
    state = ProfileApplyState(schema_version=1, managed_files=plan.managed_files)
    _write_state(state_path, state)
    _validate_control_path(
        journal_path,
        kind="profile apply journal",
        require_regular_file=True,
    )
    remove_journal(journal_path)
    return ProfileApplyReport(
        copied=tuple(copied),
        deleted=tuple(deleted),
        state_path=state_path,
        state=state,
    )


def apply_profile(manifest_path: Path, *, state_path: Path | None = None) -> ProfileApplyReport:
    """Apply one immutable manifest, recovering any prior journal first."""

    manifest_file = Path(manifest_path)
    state_file = _state_path(manifest_file, state_path)
    with _exclusive_lock(_lock_path(state_file)):
        _recover_pending(state_file)
        return _apply_manifest(manifest_file, state_file)


__all__ = ["apply_profile"]
