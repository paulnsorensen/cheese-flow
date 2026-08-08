"""Behavioral tests for the frozen profile-domain contract."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.models import (
    CompiledFile,
    CompiledProfileManifest,
    CompileTarget,
    DriftRecord,
    LaunchSpec,
    ProfileApplyState,
    ProjectPermissionsRequest,
)
from pydantic import ValidationError

_GENERATION = "a" * 64


def _target() -> CompileTarget:
    return CompileTarget(
        name="home",
        symbolic_root="$HOME",
        resolved_root=Path("/home/example"),
        harnesses=("claude",),
    )


def _file(
    *,
    fragment_path: str = "generations/a/claude/profile.json",
    mode: int = 0o600,
) -> CompiledFile:
    return CompiledFile(
        target="home",
        harness="claude",
        fragment_path=PurePosixPath(fragment_path),
        destination_path=PurePosixPath(".config/cheese/profile.json"),
        sha256=_GENERATION,
        mode=mode,
    )


def _manifest(**overrides: object) -> CompiledProfileManifest:
    values: dict[str, object] = {
        "schema_version": 1,
        "generation": _GENERATION,
        "profile": "live",
        "source_id": "profiles/live",
        "compile_targets": (_target(),),
        "files": (_file(),),
        "drift": (),
    }
    values.update(overrides)
    return CompiledProfileManifest(**values)


@pytest.mark.parametrize("schema_version", [0, 2, "1"])
def test_manifest_rejects_schema_versions_other_than_v1(schema_version: object) -> None:
    with pytest.raises(ValidationError):
        _manifest(schema_version=schema_version)


@pytest.mark.parametrize("schema_version", [0, 2, "1"])
def test_apply_state_rejects_schema_versions_other_than_v1(schema_version: object) -> None:
    with pytest.raises(ValidationError):
        ProfileApplyState(schema_version=schema_version, managed_files=(Path("/tmp/owned"),))


@pytest.mark.parametrize(
    "generation",
    [
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "" * 64,
    ],
)
def test_manifest_rejects_generations_that_are_not_lowercase_sha256(
    generation: str,
) -> None:
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        _manifest(generation=generation)


@pytest.mark.parametrize(
    "field_name, value",
    [
        ("source_id", "/profiles/live"),
        ("source_id", "../outside"),
        ("source_id", "profiles/../outside"),
    ],
)
def test_manifest_rejects_non_relative_source_ids(field_name: str, value: str) -> None:
    with pytest.raises(ValidationError, match="relative"):
        _manifest(**{field_name: value})


@pytest.mark.parametrize("fragment_path", ["/absolute/file", "../outside", "nested/../../outside"])
def test_compiled_file_rejects_escaping_fragment_paths(fragment_path: str) -> None:
    with pytest.raises(ValidationError, match="relative|path components"):
        _file(fragment_path=fragment_path)


@pytest.mark.parametrize(
    "destination_path", ["/absolute/file", "../outside", "nested/../../outside"]
)
def test_compiled_file_rejects_escaping_destination_paths(destination_path: str) -> None:
    with pytest.raises(ValidationError, match="relative|path components"):
        CompiledFile(
            target="home",
            harness="claude",
            fragment_path=PurePosixPath("fragment.json"),
            destination_path=PurePosixPath(destination_path),
            sha256=_GENERATION,
        )


@pytest.mark.parametrize("mode", [True, 0o1000, -1, "755"])
def test_compiled_file_rejects_non_posix_modes(mode: object) -> None:
    with pytest.raises(ValidationError, match="permission mode"):
        _file(mode=mode)


def test_compiled_file_defaults_to_private_mode() -> None:
    assert _file().mode == 0o600


@pytest.mark.parametrize(
    "destination_path", ["/absolute/file", "../outside", "nested/../../outside"]
)
def test_drift_rejects_escaping_destination_paths(destination_path: str) -> None:
    with pytest.raises(ValidationError, match="relative|path components"):
        DriftRecord(
            target="home",
            destination_path=PurePosixPath(destination_path),
            path="/home/example/.config/cheese/profile.json",
            baseline={},
            live={},
            compiled={},
        )


def test_drift_json_values_are_recursively_frozen_and_json_serializable() -> None:
    baseline = {"nested": {"items": [{"enabled": True}]}}
    record = DriftRecord(
        target="home",
        destination_path=PurePosixPath(".config/cheese/profile.json"),
        path="nested.items",
        baseline=baseline,
        live={"nested": {"items": [{"enabled": False}]}},
        compiled={"nested": {"items": [{"enabled": True}]}},
    )

    baseline["nested"]["items"][0]["enabled"] = False
    assert record.baseline["nested"]["items"][0]["enabled"] is True  # type: ignore[index]
    with pytest.raises(TypeError):
        record.baseline["nested"]["items"][0]["enabled"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        record.baseline["nested"]["items"][0] = {}  # type: ignore[index]

    dumped = record.model_dump(mode="json")
    assert dumped["baseline"] == {"nested": {"items": [{"enabled": True}]}}
    dumped["baseline"]["nested"]["items"][0]["enabled"] = False  # type: ignore[index]
    assert record.baseline["nested"]["items"][0]["enabled"] is True  # type: ignore[index]
    assert json.loads(record.model_dump_json())["baseline"] == {
        "nested": {"items": [{"enabled": True}]}
    }

    manifest_dump = _manifest(drift=(record,)).model_dump(mode="json")
    assert manifest_dump["drift"] == [record.model_dump(mode="json")]
    assert (
        json.loads(json.dumps(manifest_dump, sort_keys=True, separators=(",", ":")))
        == manifest_dump
    )


def test_apply_state_rejects_relative_owned_paths() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        ProfileApplyState(schema_version=1, managed_files=(Path("relative/file"),))


def test_launch_spec_snapshots_and_hides_environment() -> None:
    caller_environment = {"PROFILE_SECRET": "top-secret", "HOME": "/tmp/home"}
    spec = LaunchSpec(
        executable="claude",
        argv=("claude", "--version"),
        environment=caller_environment,
    )

    caller_environment["PROFILE_SECRET"] = "changed"
    caller_environment["NEW_VALUE"] = "not-owned"

    assert dict(spec.environment) == {"PROFILE_SECRET": "top-secret", "HOME": "/tmp/home"}
    with pytest.raises(TypeError):
        spec.environment["PROFILE_SECRET"] = "changed"  # type: ignore[index]

    representation = repr(spec)
    assert "environment" not in representation
    assert "top-secret" not in representation
    assert "top-secret" not in str(spec.model_dump())
    assert "top-secret" not in spec.model_dump_json()
    assert spec.model_dump() == {"executable": "claude", "argv": ("claude", "--version")}


def test_project_permissions_request_has_closed_defaults() -> None:
    request = ProjectPermissionsRequest(project_root=Path("/project"))
    assert request.local is False
    assert request.harnesses == ("claude", "codex")


def test_profile_models_are_frozen() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError):
        manifest.profile = "other"  # type: ignore[misc]
