"""Render a standalone project's Claude and Codex permission fragment."""

from __future__ import annotations

import contextlib
import os
import stat
import uuid
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import ValidationError

from .errors import ProfilePermissionsError
from .models import ProjectPermissionsReport, ProjectPermissionsRequest
from .parse import ResolvedProfile
from .project_permissions_claude import (
    plan_project_permissions as plan_claude_project_permissions,
)
from .project_permissions_codex import (
    plan_project_permissions as plan_codex_project_permissions,
)

_SUPPORTED_HARNESSES = ("claude", "codex")
_PERMISSION_KEYS = ("permissions_allow", "permissions_deny")

__all__ = ["render_project_permissions"]


def _validate_explicit_project_root(project_root: Path) -> Path:
    try:
        candidate = Path(project_root)
    except TypeError as exc:
        raise ProfilePermissionsError("project_root must be an explicit path") from exc
    if not candidate.is_absolute():
        raise ProfilePermissionsError("project_root must be absolute and explicit")
    try:
        root_stat = os.lstat(candidate)
    except OSError as exc:
        raise ProfilePermissionsError(f"project_root is not usable: {candidate}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ProfilePermissionsError(f"project_root is not a directory: {candidate}")
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProfilePermissionsError(f"project_root is not usable: {candidate}") from exc
    if not root.is_dir():
        raise ProfilePermissionsError(f"project_root is not a directory: {candidate}")
    return root


def _permission_fragment(root: Path) -> Path:
    fragment = root / ".agent-profiles" / "_permissions" / "profile.yaml"
    try:
        resolved = fragment.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ProfilePermissionsError(f"could not resolve permission fragment: {fragment}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProfilePermissionsError(
            f"permission fragment escapes project root: {fragment}"
        ) from exc
    if not fragment.is_file():
        raise ProfilePermissionsError(f"permission fragment was not found: {fragment}")
    return fragment


def _parse_standalone_permission_profile(
    fragment: Path,
    *,
    environment: Mapping[str, str],
) -> ResolvedProfile:
    """Parse only the fixed permission fragment, never a profile source root."""
    del environment
    try:
        raw = yaml.safe_load(fragment.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProfilePermissionsError(
            f"could not read permission fragment {fragment}: {exc}"
        ) from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ProfilePermissionsError(f"permission fragment {fragment} must be a YAML mapping")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ProfilePermissionsError(f"permission fragment {fragment} is missing a profile name")
    description = raw.get("description") or ""
    if not isinstance(description, str):
        raise ProfilePermissionsError(
            f"permission fragment {fragment} description must be a string"
        )

    settings = raw.get("settings")
    if settings is None:
        settings = {}
    if not isinstance(settings, Mapping):
        raise ProfilePermissionsError(
            f"permission fragment {fragment} settings must be a YAML mapping"
        )

    try:
        return ResolvedProfile.model_validate(
            {
                "name": name,
                "description": description,
                "source_id": ".agent-profiles/_permissions",
                "settings": dict(settings),
                "permissions_allow": settings.get("permissions_allow", ()),
                "permissions_deny": settings.get("permissions_deny", ()),
            }
        )
    except ValidationError as exc:
        raise ProfilePermissionsError(f"invalid permission fragment {fragment}: {exc}") from exc


def _validate_nested_permission_settings(profile: ResolvedProfile, fragment: Path) -> None:
    settings = profile.settings
    if not isinstance(settings, Mapping) or not any(key in settings for key in _PERMISSION_KEYS):
        raise ProfilePermissionsError(
            f"permission fragment {fragment} defines no permissions under `settings:`; "
            "add settings.permissions_allow and/or settings.permissions_deny"
        )


def _validate_harnesses(request: ProjectPermissionsRequest) -> tuple[str, ...]:
    try:
        harnesses = tuple(request.harnesses)
    except TypeError as exc:
        raise ProfilePermissionsError("project permission harnesses must be a sequence") from exc
    unsupported = tuple(harness for harness in harnesses if harness not in _SUPPORTED_HARNESSES)
    if unsupported:
        names = ", ".join(repr(harness) for harness in unsupported)
        raise ProfilePermissionsError(
            f"unsupported project permission harness {names}; expected claude, codex"
        )
    return harnesses


def _plan_harness(
    harness: str,
    profile: ResolvedProfile,
    root: Path,
    *,
    local: bool,
) -> tuple[tuple[Path, bytes], ...]:
    if harness == "claude":
        return plan_claude_project_permissions(profile, root, local=local)
    return plan_codex_project_permissions(profile, root, local=local)


def _validate_lexical_parent_chain(root: Path, path: Path) -> None:
    try:
        root_metadata = os.lstat(root)
    except OSError as exc:
        raise ProfilePermissionsError(
            f"could not inspect permission write parent: {root} (destination: {path})"
        ) from exc
    if stat.S_ISLNK(root_metadata.st_mode):
        raise ProfilePermissionsError(
            f"permission write parent must not be a symlink: {root} (destination: {path})"
        )
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ProfilePermissionsError(
            f"permission write parent is not a directory: {root} (destination: {path})"
        )
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ProfilePermissionsError(
            f"permission write destination escapes project root: {path}"
        ) from exc

    parent = root
    for component in relative.parts[:-1]:
        parent /= component
        try:
            metadata = os.lstat(parent)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ProfilePermissionsError(
                f"could not inspect permission write parent: {parent} (destination: {path})"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ProfilePermissionsError(
                f"permission write parent must not be a symlink: {parent} (destination: {path})"
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise ProfilePermissionsError(
                f"permission write parent is not a directory: {parent} (destination: {path})"
            )


def _validate_planned_destinations(
    root: Path,
    planned: tuple[tuple[Path, bytes], ...],
) -> tuple[tuple[Path, bytes], ...]:
    validated: list[tuple[Path, bytes]] = []
    for item in planned:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ProfilePermissionsError("permission renderer returned an invalid write plan")
        raw_path, payload = item
        if not isinstance(raw_path, Path):
            try:
                path = Path(raw_path)
            except TypeError as exc:
                raise ProfilePermissionsError(
                    "permission write destination must be a path"
                ) from exc
        else:
            path = raw_path
        if not path.is_absolute():
            raise ProfilePermissionsError(f"permission write destination must be absolute: {path}")
        if not isinstance(payload, bytes):
            raise ProfilePermissionsError(f"permission write payload must be bytes: {path}")
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ProfilePermissionsError(
                f"could not resolve permission write destination: {path}"
            ) from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ProfilePermissionsError(
                f"permission write destination escapes project root: {path}"
            ) from exc
        if resolved == root:
            raise ProfilePermissionsError(
                f"permission write destination must be below project root: {path}"
            )
        if path.exists() and not path.is_file():
            raise ProfilePermissionsError(f"permission write destination is not a file: {path}")
        _validate_lexical_parent_chain(root, path)
        validated.append((path, payload))
    return tuple(validated)


def _open_parent_directory(root: Path, path: Path) -> int:
    relative = path.relative_to(root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory_fd = os.open(root, flags)
    except OSError as exc:
        raise ProfilePermissionsError(
            f"permission write parent is not a directory: {root} (destination: {path})"
        ) from exc

    try:
        for component in relative.parts[:-1]:
            try:
                child_fd = os.open(component, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, dir_fd=directory_fd)
                child_fd = os.open(component, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
    except BaseException:
        os.close(directory_fd)
        raise
    return directory_fd


def _atomic_replace(root: Path, path: Path, payload: bytes) -> None:
    _validate_lexical_parent_chain(root, path)
    parent_fd = _open_parent_directory(root, path)

    temporary: str | None = None
    try:
        _validate_lexical_parent_chain(root, path)
        parent_metadata = os.fstat(parent_fd)
        lexical_metadata = os.lstat(path.parent)
        if (
            parent_metadata.st_dev,
            parent_metadata.st_ino,
        ) != (
            lexical_metadata.st_dev,
            lexical_metadata.st_ino,
        ):
            raise ProfilePermissionsError(
                f"permission write parent changed during publication: {path.parent} "
                f"(destination: {path})"
            )
        while temporary is None:
            candidate = f".{path.name}.{uuid.uuid4().hex}.tmp"
            try:
                handle = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary = candidate

        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        _validate_lexical_parent_chain(root, path)
        lexical_metadata = os.lstat(path.parent)
        if (
            parent_metadata.st_dev,
            parent_metadata.st_ino,
        ) != (
            lexical_metadata.st_dev,
            lexical_metadata.st_ino,
        ):
            raise ProfilePermissionsError(
                f"permission write parent changed during publication: {path.parent} "
                f"(destination: {path})"
            )
        os.replace(
            temporary,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary = None
    finally:
        if temporary is not None:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent_fd)
        os.close(parent_fd)


def _atomic_replace_each_planned_file(
    root: Path,
    planned: tuple[tuple[Path, bytes], ...],
) -> None:
    for path, payload in planned:
        _validate_lexical_parent_chain(root, path)
        try:
            _atomic_replace(root, path, payload)
        except (OSError, RuntimeError) as exc:
            raise ProfilePermissionsError(f"could not write permission file {path}") from exc


def render_project_permissions(
    request: ProjectPermissionsRequest,
    *,
    environment: Mapping[str, str],
) -> ProjectPermissionsReport:
    """Render the fixed project permission fragment without source discovery."""
    harnesses = _validate_harnesses(request)
    root = _validate_explicit_project_root(request.project_root)
    fragment = _permission_fragment(root)
    profile = _parse_standalone_permission_profile(fragment, environment=environment)
    _validate_nested_permission_settings(profile, fragment)

    planned: list[tuple[Path, bytes]] = []
    skipped: list[str] = []
    for harness in harnesses:
        if request.local and harness == "codex":
            skipped.append(harness)
            continue
        planned.extend(_plan_harness(harness, profile, root, local=request.local))

    validated = _validate_planned_destinations(root, tuple(planned))
    _atomic_replace_each_planned_file(root, validated)
    return ProjectPermissionsReport(
        written=tuple(path for path, _ in validated),
        skipped_harnesses=tuple(skipped),
    )
