"""Build validated profile launch specifications without executing harnesses."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cheese_flow.profiles.errors import ProfileError, ProfileLaunchError
from cheese_flow.profiles.isolation.registry import isolation_builder_for
from cheese_flow.profiles.isolation.runtime import build_workspace, remove_workspace
from cheese_flow.profiles.launch_policy import validate_launch_policy
from cheese_flow.profiles.models import LaunchRequest, LaunchSpec
from cheese_flow.profiles.renderers.registry import renderer
from cheese_flow.profiles.source import load_profile


def _snapshot_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Copy and validate the caller-owned environment without exposing values."""
    if not isinstance(environment, Mapping):
        raise ProfileLaunchError("launch environment must be a mapping")
    try:
        snapshot = dict(environment)
    except Exception:
        raise ProfileLaunchError("launch environment could not be copied") from None
    for key, value in snapshot.items():
        if not isinstance(key, str) or not key:
            raise ProfileLaunchError("launch environment keys must be non-empty strings")
        if "=" in key:
            raise ProfileLaunchError("launch environment keys must not contain '='")
        if not isinstance(value, str):
            raise ProfileLaunchError("launch environment values must be strings")
        if "\x00" in key or "\x00" in value:
            raise ProfileLaunchError("launch environment must not contain NUL bytes")
    return snapshot


def _merge_profile_environment(
    environment: Mapping[str, str], profile_environment: Mapping[str, str]
) -> dict[str, str]:
    """Apply profile declarations over the independent caller environment."""
    caller = _snapshot_environment(environment)
    declared = _snapshot_environment(profile_environment)
    return {**caller, **declared}


def _validate_exec_inputs(
    executable: object, argv: object, environment: object
) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Validate the exact values accepted by ``os.execvpe``."""
    if not isinstance(executable, str) or not executable:
        raise ProfileLaunchError("launch executable must be a non-empty string")
    if "\x00" in executable:
        raise ProfileLaunchError("launch executable must not contain NUL bytes")
    if isinstance(argv, (str, bytes, bytearray)) or not isinstance(argv, Sequence):
        raise ProfileLaunchError("launch argv must be a sequence of strings")
    try:
        values = tuple(argv)
    except Exception:
        raise ProfileLaunchError("launch argv must be a sequence of strings") from None
    if not values or any(not isinstance(value, str) for value in values):
        raise ProfileLaunchError("launch argv must contain only strings")
    if any("\x00" in value for value in values):
        raise ProfileLaunchError("launch argv must not contain NUL bytes")
    if values[0] != executable:
        raise ProfileLaunchError("launch argv must include executable as argv0")
    if not isinstance(environment, Mapping):
        raise ProfileLaunchError("launch environment must be a mapping")
    snapshot = _snapshot_environment(environment)
    return executable, values, snapshot


def _complete_launch_spec(value: Any) -> LaunchSpec:
    """Require the complete executable projection returned by a builder."""
    if not isinstance(value, LaunchSpec):
        raise ProfileLaunchError("launch projection did not return a LaunchSpec")
    _validate_exec_inputs(value.executable, value.argv, value.environment)
    return value


def _redact_error(error: ProfileError, environment: Mapping[str, str]) -> ProfileError:
    """Rebuild a profile error without explicit environment values."""
    message = str(error)
    for value in environment.values():
        if value:
            message = message.replace(value, "<redacted>")
    return type(error)(message)


def _build_launch_with_workspace(
    request: LaunchRequest, *, environment: Mapping[str, str]
) -> tuple[LaunchSpec, Path | None]:
    """Build a launch spec and retain an isolated workspace for CLI cleanup."""
    if not isinstance(request, LaunchRequest):
        raise ProfileLaunchError("launch requires a LaunchRequest")
    environment_snapshot = _snapshot_environment(environment)
    profile: Any = None
    failure: ProfileError | None = None
    try:
        profile = load_profile(
            request.source_root,
            request.profile_name,
            environment=environment_snapshot,
        )
        policy = validate_launch_policy(
            profile,
            request.harness,
            request.arguments,
        )
        launch_environment = _merge_profile_environment(environment_snapshot, profile.env)
        _validate_exec_inputs(
            policy.harness,
            (policy.harness, *policy.profile_arguments, *policy.caller_arguments),
            launch_environment,
        )

        if policy.isolated:
            builder = isolation_builder_for(policy.harness)
            built: LaunchSpec | None = None

            def build(root: Path) -> None:
                nonlocal built
                built = _complete_launch_spec(
                    builder(
                        profile,
                        policy,
                        root,
                        environment=environment_snapshot,
                    )
                )

            workspace = build_workspace(environment_snapshot, build)
            if built is None:
                try:
                    remove_workspace(workspace)
                except Exception:
                    raise ProfileLaunchError(
                        "isolated launch did not produce a LaunchSpec; workspace cleanup failed"
                    ) from None
                raise ProfileLaunchError("isolated launch did not produce a LaunchSpec")
            return built, workspace

        spec = renderer(policy.harness).launch_spec(
            profile,
            None,
            policy.caller_arguments,
            launch_environment,
        )
        return _complete_launch_spec(spec), None
    except ProfileError as exc:
        redaction_environment: Mapping[str, str] = environment_snapshot
        if profile is not None:
            with contextlib.suppress(Exception):
                redaction_environment = {
                    **environment_snapshot,
                    **_snapshot_environment(profile.env),
                }
        try:
            failure = _redact_error(exc, redaction_environment)
        except Exception:
            failure = ProfileLaunchError("could not build launch")
    except Exception:
        failure = ProfileLaunchError("could not build launch")
    if failure is not None:
        raise failure
    raise ProfileLaunchError("could not build launch")


def build_launch(request: LaunchRequest, *, environment: Mapping[str, str]) -> LaunchSpec:
    """Resolve and validate one profile launch without executing its harness."""
    spec, _workspace = _build_launch_with_workspace(request, environment=environment)
    return spec


__all__ = ["build_launch"]
