"""Frozen domain contracts for the extracted profile engine.

The profile engine deliberately keeps its public data shapes independent from
installation plans.  Paths that identify generated content are POSIX-relative
identities; live paths remain ordinary ``Path`` values and are validated by the
operation that owns the filesystem boundary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
)

CompileHarnessName = Literal["claude", "codex", "copilot", "crush", "cursor", "opencode"]
LaunchHarnessName = CompileHarnessName
IsolatedLaunchHarnessName = Literal["claude", "codex", "opencode"]
ProjectPermissionHarnessName = Literal["claude", "codex"]

FrozenEnvironment: TypeAlias = Mapping[str, str]

_GENERATION_RE = re.compile(r"[0-9a-f]{64}")


class _FrozenModel(BaseModel):
    """Shared configuration for public immutable profile models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _relative_posix_path(value: object, field_name: str) -> PurePosixPath:
    """Validate and normalize one non-empty POSIX-relative path identity."""

    if isinstance(value, (PurePosixPath, Path)):
        raw = value.as_posix()
    elif isinstance(value, str):
        raw = value
    else:
        raise TypeError(f"{field_name} must be a POSIX-relative path")

    if not raw or raw == "." or raw.startswith("/"):
        raise ValueError(f"{field_name} must be a non-empty relative path")
    if "\x00" in raw:
        raise ValueError(f"{field_name} must not contain NUL bytes")
    if ".." in raw.split("/"):
        raise ValueError(f"{field_name} must be relative and contain no '..' path components")

    path = PurePosixPath(raw)
    if path.is_absolute() or path == PurePosixPath("."):
        raise ValueError(f"{field_name} must be a non-empty relative path")
    return path


def _absolute_paths(value: tuple[Path, ...], field_name: str) -> tuple[Path, ...]:
    relative = tuple(str(path) for path in value if not path.is_absolute())
    if relative:
        raise ValueError(f"{field_name} must contain absolute paths: {', '.join(relative)}")
    return value


def _freeze_json(value: object) -> object:
    """Snapshot JSON containers into recursively immutable values."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: object) -> object:
    """Return ordinary JSON containers for explicit model serialization."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(child) for child in value]
    return value


class CompileRequest(_FrozenModel):
    """Inputs for one explicit profile compilation."""

    profile_name: str
    source_root: Path
    baseline_root: Path
    output_root: Path


class CompileTarget(_FrozenModel):
    """One named symbolic deployment root and its harness ownership."""

    name: str
    symbolic_root: str
    resolved_root: Path
    harnesses: tuple[CompileHarnessName, ...]

    @field_validator("resolved_root")
    @classmethod
    def _resolved_root_is_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("resolved_root must be an absolute path")
        return value


class CompiledFile(_FrozenModel):
    """One generated fragment and its relative destination."""

    target: str
    harness: CompileHarnessName
    fragment_path: PurePosixPath
    destination_path: PurePosixPath
    sha256: str
    mode: int = 0o600

    @field_validator("mode", mode="before")
    @classmethod
    def _mode_is_posix_permissions(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0o777:
            raise ValueError(
                "mode must be an integer POSIX permission mode from 0o000 through 0o777"
            )
        return value

    @field_validator("fragment_path", "destination_path", mode="before")
    @classmethod
    def _relative_paths(cls, value: object, info) -> PurePosixPath:
        return _relative_posix_path(value, info.field_name)


class DriftRecord(_FrozenModel):
    """One difference between baseline, live, and compiled values."""

    target: str
    destination_path: PurePosixPath
    path: str
    baseline: JsonValue
    live: JsonValue
    compiled: JsonValue

    @field_validator("destination_path", mode="before")
    @classmethod
    def _relative_destination(cls, value: object, info) -> PurePosixPath:
        return _relative_posix_path(value, info.field_name)

    @field_validator("baseline", "live", "compiled", mode="after")
    @classmethod
    def _freeze_json_fields(cls, value: JsonValue) -> JsonValue:
        return _freeze_json(value)  # type: ignore[return-value]

    @field_serializer("baseline", "live", "compiled", when_used="always")
    def _serialize_json_fields(self, value: JsonValue) -> JsonValue:
        return _thaw_json(value)  # type: ignore[return-value]


class CompiledProfileManifest(_FrozenModel):
    """Schema-v1 immutable publication produced by profile compilation."""

    schema_version: Literal[1]
    generation: str
    profile: str
    source_id: str
    compile_targets: tuple[CompileTarget, ...]
    files: tuple[CompiledFile, ...]
    drift: tuple[DriftRecord, ...]

    @field_validator("generation")
    @classmethod
    def _generation_is_lowercase_sha256(cls, value: str) -> str:
        if _GENERATION_RE.fullmatch(value) is None:
            raise ValueError("generation must be exactly 64 lowercase hexadecimal characters")
        return value

    @field_validator("source_id", mode="before")
    @classmethod
    def _source_id_is_relative(cls, value: object) -> str:
        _relative_posix_path(value, "source_id")
        return str(value)


class ProfileApplyState(_FrozenModel):
    """Schema-v1 set of live paths currently owned by profile apply."""

    schema_version: Literal[1]
    managed_files: tuple[Path, ...]

    @field_validator("managed_files")
    @classmethod
    def _managed_files_are_absolute(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        return _absolute_paths(value, "managed_files")


class ProfileApplyReport(_FrozenModel):
    """Exact paths copied/deleted and the committed ownership state."""

    copied: tuple[Path, ...]
    deleted: tuple[Path, ...]
    state_path: Path
    state: ProfileApplyState


class LaunchRequest(_FrozenModel):
    """Inputs for policy validation and launch-spec construction."""

    profile_name: str
    source_root: Path
    harness: LaunchHarnessName
    arguments: tuple[str, ...]


class LaunchSpec(_FrozenModel):
    """Validated executable projection with a private environment snapshot."""

    executable: str
    argv: tuple[str, ...]
    environment: FrozenEnvironment = Field(repr=False, exclude=True)

    @field_validator("environment", mode="after")
    @classmethod
    def _snapshot_environment(cls, value: Mapping[str, str]) -> FrozenEnvironment:
        # Pydantic has already copied Mapping input into a plain dict.  Make the
        # copy explicit as well so this remains true for custom Mapping inputs.
        return MappingProxyType(dict(value))


class ProjectPermissionsRequest(_FrozenModel):
    """Explicit project root and closed Claude/Codex permission selection."""

    project_root: Path
    local: bool = False
    harnesses: tuple[ProjectPermissionHarnessName, ...] = ("claude", "codex")


class ProjectPermissionsReport(_FrozenModel):
    """Exact project files written and harnesses intentionally skipped."""

    written: tuple[Path, ...]
    skipped_harnesses: tuple[ProjectPermissionHarnessName, ...]


__all__ = [
    "CompileHarnessName",
    "CompileRequest",
    "CompileTarget",
    "CompiledFile",
    "CompiledProfileManifest",
    "DriftRecord",
    "FrozenEnvironment",
    "IsolatedLaunchHarnessName",
    "LaunchHarnessName",
    "LaunchRequest",
    "LaunchSpec",
    "ProfileApplyReport",
    "ProfileApplyState",
    "ProjectPermissionHarnessName",
    "ProjectPermissionsReport",
    "ProjectPermissionsRequest",
]
