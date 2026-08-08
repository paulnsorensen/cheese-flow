"""Filesystem boundaries for explicit profile sources."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .errors import ProfileSourceError

_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def validate_name(value: object, *, kind: str) -> str:
    """Validate a profile or item identifier before it becomes a path."""
    if not isinstance(value, str) or not value:
        raise ProfileSourceError(f"{kind} must be a non-empty name")
    if value in {".", ".."} or _NAME_RE.fullmatch(value) is None:
        raise ProfileSourceError(
            f"invalid {kind} {value!r} (must match [A-Za-z0-9._-]+ and not be '.' or '..')"
        )
    return value


def validate_relative_path(value: object, *, kind: str, allow_empty: bool = False) -> str:
    """Validate a POSIX-relative declaration without touching the filesystem."""
    if not isinstance(value, str):
        raise ProfileSourceError(f"{kind} must be a relative path")
    if not value:
        if allow_empty:
            return value
        raise ProfileSourceError(f"{kind} must be a non-empty relative path")
    if "\x00" in value:
        raise ProfileSourceError(f"{kind} must not contain NUL bytes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ProfileSourceError(f"{kind} must be relative and contain no '..' components")
    if path == PurePosixPath("."):
        raise ProfileSourceError(f"{kind} must not be the current directory")
    return value


def validate_explicit_source_root(source_root: Path) -> Path:
    """Return the canonical caller-owned source root.

    Relative roots are rejected instead of being interpreted against process
    cwd.  No environment or home fallback is part of this boundary.
    """
    try:
        candidate = Path(source_root)
    except TypeError as exc:
        raise ProfileSourceError("source_root must be a path") from exc
    if not candidate.is_absolute():
        raise ProfileSourceError("source_root must be absolute and explicit")
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProfileSourceError(f"source_root is not usable: {candidate}") from exc
    if not root.is_dir():
        raise ProfileSourceError(f"source_root is not a directory: {candidate}")
    return root


def _within(root: Path, candidate: Path, *, kind: str) -> Path:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ProfileSourceError(f"{kind} escapes source root: {candidate}") from exc
    return candidate


def resolve_within(root: Path, candidate: Path, *, kind: str) -> Path:
    """Canonicalize a path and reject symlink or lexical escapes."""
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ProfileSourceError(f"could not resolve {kind}: {candidate}") from exc
    return _within(root, resolved, kind=kind)


def source_profiles_root(source_root: Path) -> Path:
    """Resolve the required ``<source-root>/profiles`` directory safely."""
    profiles = resolve_within(source_root, source_root / "profiles", kind="profiles root")
    if not profiles.is_dir():
        raise ProfileSourceError(f"profiles root is not a directory: {source_root / 'profiles'}")
    return profiles


def resolve_profile_dir(source_root: Path, profile_name: str) -> Path:
    """Resolve one named profile before inspecting its contents."""
    profiles = source_profiles_root(source_root)
    validate_name(profile_name, kind="profile name")
    profile_dir = resolve_within(
        source_root, profiles / profile_name, kind=f"profile {profile_name!r}"
    )
    if not profile_dir.is_dir():
        raise ProfileSourceError(f"profile {profile_name!r} was not found under {profiles}")
    return profile_dir


def resolve_declared_path(source_root: Path, value: object, *, kind: str) -> Path:
    """Resolve a profile-declared source path under the explicit root."""
    relative = validate_relative_path(value, kind=kind)
    posix = PurePosixPath(relative)
    candidate = source_root.joinpath(*posix.parts)
    return resolve_within(source_root, candidate, kind=kind)


def resolve_profile_file(source_root: Path, profile_dir: Path, name: str) -> Path:
    """Resolve a file directly under a profile directory safely."""
    candidate = resolve_within(source_root, profile_dir / name, kind=name)
    if not candidate.is_file():
        raise ProfileSourceError(f"required profile file was not found: {profile_dir / name}")
    return candidate


def source_id(source_root: Path, path: Path) -> str:
    """Return a stable POSIX identity relative to the source root."""
    try:
        relative = path.relative_to(source_root)
    except ValueError as exc:
        raise ProfileSourceError(f"profile path escapes source root: {path}") from exc
    value = PurePosixPath(*relative.parts).as_posix()
    if not value or value == ".":
        raise ProfileSourceError("profile source id must be a non-empty relative path")
    return value
