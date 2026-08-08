"""Behavioral tests for profile launch dispatch."""

from __future__ import annotations

import stat
import traceback
from pathlib import Path

import cheese_flow.profiles.launch as launch_module
import pytest
from cheese_flow.profiles.errors import ProfileLaunchError, ProfileSourceError
from cheese_flow.profiles.isolation.registry import isolation_builder_for
from cheese_flow.profiles.isolation.runtime import remove_workspace
from cheese_flow.profiles.launch import _build_launch_with_workspace, build_launch
from cheese_flow.profiles.models import LaunchRequest


def _profile(source_root: Path, *, isolated: bool = False, env: str = "") -> None:
    profile_dir = source_root / "profiles" / "demo"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("profile.yaml").write_text(
        f"name: demo\nisolated: {str(isolated).lower()}\n{env}",
        encoding="utf-8",
    )


def test_non_isolated_launch_builds_argv_and_secret_safe_environment_snapshot(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, env="env:\n  PROFILE_TOKEN: profile-secret\n")
    environment = {"HOME": str(tmp_path / "home"), "TOKEN": "caller-secret"}
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="copilot",
        arguments=("--version",),
    )

    spec = build_launch(request, environment=environment)
    environment["TOKEN"] = "changed"

    assert spec.executable == "copilot"
    assert spec.argv == ("copilot", "--version")
    assert dict(spec.environment) == {
        "HOME": str(tmp_path / "home"),
        "TOKEN": "caller-secret",
        "PROFILE_TOKEN": "profile-secret",
    }
    assert "caller-secret" not in repr(spec)
    assert "profile-secret" not in repr(spec)
    assert spec.model_dump() == {
        "executable": "copilot",
        "argv": ("copilot", "--version"),
    }
    with pytest.raises(TypeError):
        spec.environment["TOKEN"] = "changed"  # type: ignore[index]


def test_isolated_launch_returns_complete_spec_and_private_workspace(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, isolated=True)
    environment = {
        "HOME": str(tmp_path / "home"),
        "XDG_RUNTIME_DIR": str(tmp_path / "runtime"),
    }
    Path(environment["XDG_RUNTIME_DIR"]).mkdir()
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="opencode",
        arguments=("--version",),
    )

    spec, workspace = _build_launch_with_workspace(request, environment=environment)

    assert spec.executable == "opencode"
    assert spec.argv == ("opencode", "--version")
    assert workspace is not None
    assert workspace.is_dir()
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert dict(spec.environment)["OPENCODE_DISABLE_PROJECT_CONFIG"] == "true"
    remove_workspace(workspace)
    assert not workspace.exists()


def test_isolated_launch_postcondition_cleanup_failure_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, isolated=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    environment = {
        "HOME": str(tmp_path / "home"),
        "XDG_RUNTIME_DIR": str(runtime),
    }
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="opencode",
        arguments=("--version",),
    )

    monkeypatch.setattr(launch_module, "_complete_launch_spec", lambda value: None)

    def fail_cleanup(workspace: Path) -> None:
        raise RuntimeError("cleanup secret")

    monkeypatch.setattr(launch_module, "remove_workspace", fail_cleanup)

    with pytest.raises(
        ProfileLaunchError,
        match="did not produce a LaunchSpec; workspace cleanup failed",
    ):
        _build_launch_with_workspace(request, environment=environment)


@pytest.mark.parametrize(
    ("harness", "argument"),
    [
        ("opencode", "--auto"),
        ("opencode", "-a"),
        ("codex", "--search"),
        ("codex", "--remote"),
    ],
)
def test_policy_flags_never_reach_argv_or_allocate_workspace(
    tmp_path: Path, harness: str, argument: str
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, isolated=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness=harness,  # type: ignore[arg-type]
        arguments=(argument,),
    )

    with pytest.raises(ProfileLaunchError, match="cannot override profile launch policy"):
        build_launch(
            request,
            environment={"HOME": str(tmp_path / "home"), "XDG_RUNTIME_DIR": str(runtime)},
        )

    assert not (runtime / "cheese-flow").exists()


@pytest.mark.parametrize("argument", ["serve", "--port=4096", "--cors=http://localhost"])
def test_opencode_network_surface_fails_before_workspace_allocation(
    tmp_path: Path, argument: str
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, isolated=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="opencode",
        arguments=(argument,),
    )

    with pytest.raises(ProfileLaunchError, match="network surface"):
        build_launch(
            request,
            environment={"HOME": str(tmp_path / "home"), "XDG_RUNTIME_DIR": str(runtime)},
        )

    assert not (runtime / "cheese-flow").exists()


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ("tools:\n  - read\n", "does not support tools restrictions"),
        (
            "enabled_plugins:\n  demo: true\n",
            "does not support enabled_plugins restrictions",
        ),
    ],
)
def test_unsupported_opencode_declarations_fail_before_workspace_allocation(
    tmp_path: Path, declaration: str, message: str
) -> None:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "demo"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("profile.yaml").write_text(
        f"name: demo\nisolated: true\n{declaration}",
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="opencode",
        arguments=("--version",),
    )

    with pytest.raises(ProfileLaunchError, match=message):
        build_launch(
            request,
            environment={"HOME": str(tmp_path / "home"), "XDG_RUNTIME_DIR": str(runtime)},
        )

    assert not (runtime / "cheese-flow").exists()


@pytest.mark.parametrize(
    "environment",
    [
        {"": "empty-key"},
        {"KEY=VALUE": "equals-key"},
        {"KEY\0": "value"},
        {"KEY": "value\0with-nul"},
        {1: "non-string-key"},
        {"KEY": 1},
        ["KEY"],
    ],
)
def test_invalid_exec_environment_fails_before_workspace_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: object,
) -> None:
    allocated = False

    def fail_allocate(*args: object, **kwargs: object) -> object:
        nonlocal allocated
        allocated = True
        raise AssertionError("workspace allocation must not run")

    monkeypatch.setattr("cheese_flow.profiles.launch.build_workspace", fail_allocate)
    request = LaunchRequest(
        profile_name="demo",
        source_root=tmp_path / "source",
        harness="opencode",
        arguments=(),
    )

    with pytest.raises(ProfileLaunchError, match="launch environment"):
        build_launch(request, environment=environment)  # type: ignore[arg-type]

    assert not allocated


@pytest.mark.parametrize("harness", ["cursor", "copilot", "crush"])
def test_isolated_launch_rejects_harness_without_isolation_before_workspace(
    tmp_path: Path, harness: str
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, isolated=True)
    home = tmp_path / "home"
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness=harness,  # type: ignore[arg-type]
        arguments=(),
    )

    with pytest.raises(ProfileLaunchError, match="do not support"):
        build_launch(request, environment={"HOME": str(home)})

    assert not home.exists()


@pytest.mark.parametrize("harness", ["claude", "codex", "opencode"])
def test_isolation_registry_has_only_supported_builders(harness: str) -> None:
    assert callable(isolation_builder_for(harness))  # type: ignore[arg-type]


@pytest.mark.parametrize("harness", ["copilot", "crush", "cursor"])
def test_isolation_registry_rejects_unsupported_harnesses(harness: str) -> None:
    with pytest.raises(ProfileLaunchError, match="unsupported"):
        isolation_builder_for(harness)  # type: ignore[arg-type]


def test_launch_rejects_environment_resolution_without_secret_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    _profile(source_root)
    secret = "caller-secret"

    def fail_load(*args: object, **kwargs: object) -> object:
        raise ProfileSourceError(f"profile contains {secret}")

    monkeypatch.setattr("cheese_flow.profiles.launch.load_profile", fail_load)
    request = LaunchRequest(
        profile_name="demo",
        source_root=source_root,
        harness="copilot",
        arguments=(),
    )

    with pytest.raises(ProfileSourceError) as error:
        build_launch(request, environment={"TOKEN": secret})

    formatted = "".join(traceback.format_exception(error.value))
    assert secret not in str(error.value)
    assert secret not in formatted
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "<redacted>" in str(error.value)
