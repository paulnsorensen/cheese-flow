"""Atomic live-file reconciliation for validated profile apply plans."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from .errors import ProfileApplyError
from .preflight import PlannedReplacement, PreflightPlan, revalidate_parent_chain


def _contextual_error(action: str, path: Path, error: BaseException) -> ProfileApplyError:
    return ProfileApplyError(f"could not {action} {path}: {error}")


def _revalidate(path: Path, target_root: Path, *, action: str) -> None:
    try:
        revalidate_parent_chain(path, target_root)
    except ProfileApplyError as error:
        raise _contextual_error(action, path, error) from error


def _remove_temporary(path: Path | None) -> None:
    if path is None:
        return
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _write_one(replacement: PlannedReplacement) -> Path:
    destination = Path(replacement.destination)
    target_root = Path(replacement.target_root)
    temporary: Path | None = None
    try:
        _revalidate(destination, target_root, action="replace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        _revalidate(destination, target_root, action="replace")

        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), replacement.mode)
                stream.write(replacement.content)
                stream.flush()
                os.fsync(stream.fileno())
            _revalidate(destination, target_root, action="replace")
            os.replace(temporary, destination)
            temporary = None
        finally:
            _remove_temporary(temporary)
    except ProfileApplyError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise _contextual_error("replace", destination, error) from error
    return destination


def write_replacements(plan: PreflightPlan) -> tuple[Path, ...]:
    """Atomically replace every destination in a validated apply plan."""

    replacements = sorted(plan.replacements, key=lambda item: Path(item.destination).as_posix())
    return tuple(_write_one(replacement) for replacement in replacements)


def _target_root_for_stale(plan: PreflightPlan, stale: Path) -> Path:
    roots = []
    for root in plan.target_roots:
        candidate = Path(root)
        try:
            relative = stale.relative_to(candidate)
        except ValueError:
            continue
        if relative.parts:
            roots.append(candidate)
    if not roots:
        raise ProfileApplyError(
            f"could not delete stale path {stale}: no containing target root in apply plan"
        )
    return max(roots, key=lambda root: len(root.parts))


def delete_stale(plan: PreflightPlan) -> tuple[Path, ...]:
    """Delete only validated prior-owned paths absent from the desired state."""

    stale_files = sorted(
        (Path(path) for path in plan.stale_files), key=lambda path: path.as_posix()
    )
    deleted: list[Path] = []
    for stale in stale_files:
        try:
            target_root = _target_root_for_stale(plan, stale)
            _revalidate(stale, target_root, action="delete stale path")
            stale.unlink(missing_ok=True)
        except ProfileApplyError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise _contextual_error("delete stale path", stale, error) from error
        deleted.append(stale)
    return tuple(deleted)


__all__ = ["delete_stale", "write_replacements"]
