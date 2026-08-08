"""Public profile source introspection API."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .errors import ProfileSourceError
from .parse import (
    ProfileSummary,
    ResolvedProfile,
    _load_yaml_mapping,
    _validate_profile_identity,
    resolve_profile,
)
from .paths import (
    resolve_within,
    source_id,
    source_profiles_root,
    validate_explicit_source_root,
)

__all__ = [
    "ProfileSourceError",
    "ProfileSummary",
    "ResolvedProfile",
    "list_profiles",
    "load_profile",
]


def list_profiles(source_root: Path) -> tuple[ProfileSummary, ...]:
    """List profiles directly beneath one caller-supplied source root."""
    root = validate_explicit_source_root(source_root)
    profiles_root = source_profiles_root(root)
    summaries: list[ProfileSummary] = []
    seen_names: dict[str, Path] = {}
    for entry in sorted(profiles_root.iterdir(), key=lambda path: path.name):
        profile_dir = resolve_within(root, entry, kind=f"profile {entry.name!r}")
        if not profile_dir.is_dir():
            continue
        manifest_path = resolve_within(root, profile_dir / "profile.yaml", kind="profile.yaml")
        if not manifest_path.is_file():
            continue
        raw = _load_yaml_mapping(manifest_path)
        name = _validate_profile_identity(
            profile_dir,
            raw.get("name"),
            manifest_path=manifest_path,
        )
        previous = seen_names.get(name)
        if previous is not None:
            raise ProfileSourceError(
                f"duplicate profile identity {name!r}: {previous} conflicts with {manifest_path}"
            )
        seen_names[name] = manifest_path
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise ProfileSourceError(f"{manifest_path} description must be a string")
        summaries.append(
            ProfileSummary(
                name=name,
                description=description,
                source_id=source_id(root, profile_dir),
            )
        )
    return tuple(summaries)


def load_profile(
    source_root: Path,
    profile_name: str,
    *,
    environment: Mapping[str, str],
) -> ResolvedProfile:
    """Load one profile using only the explicit source root and environment."""
    root = validate_explicit_source_root(source_root)
    return resolve_profile(root, profile_name, environment=environment)
