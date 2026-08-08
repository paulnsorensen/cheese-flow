"""Behavioral tests for isolated OpenCode launch projection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.opencode import build_opencode_isolation
from cheese_flow.profiles.launch_policy import ValidatedLaunchPolicy
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile


def _policy(
    *,
    caller_arguments: tuple[str, ...] = (),
    profile_arguments: tuple[str, ...] = (),
) -> ValidatedLaunchPolicy:
    return ValidatedLaunchPolicy(
        harness="opencode",
        isolated=True,
        caller_arguments=caller_arguments,
        profile_arguments=profile_arguments,
        warnings=(),
    )


def _profile(
    source: Path,
    *,
    system_prompt: str | None = None,
    permissions_allow: tuple[str, ...] = (),
    permissions_deny: tuple[str, ...] = (),
    settings: dict[str, object] | None = None,
    env: dict[str, str] | None = None,
    mcps: tuple[dict[str, object], ...] = (),
    tools: tuple[str, ...] = (),
    enabled_plugins: dict[str, bool] | None = None,
) -> ResolvedProfile:
    return ResolvedProfile(
        name="demo",
        description="demo profile",
        source_id="profiles/demo",
        isolated=True,
        system_prompt=system_prompt,
        settings=settings or {},
        permissions_allow=permissions_allow,
        permissions_deny=permissions_deny,
        tools=tools,
        enabled_plugins=enabled_plugins or {},
        env=env or {},
        mcps=tuple({"_source_dir": str(source), **item} for item in mcps),
    )


def test_isolated_opencode_uses_inline_config_and_protected_environment(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    prompt = tmp_path / "prompt.md"
    prompt.write_text("read-only\n", encoding="utf-8")
    profile = _profile(
        tmp_path,
        system_prompt=str(prompt),
        env={
            "PROFILE_TOKEN": "profile-secret",
            "HOME": "/profile/home",
            "XDG_CONFIG_HOME": "/profile/config",
            "XDG_DATA_HOME": "/profile/data",
            "XDG_CACHE_HOME": "/profile/cache",
            "XDG_STATE_HOME": "/profile/state",
            "OPENCODE_CONFIG": "/profile/opencode.json",
            "OPENCODE_CONFIG_DIR": "/profile/opencode-config",
            "OPENCODE_CONFIG_CONTENT": "profile must not replace isolation",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "false",
            "OPENCODE_PERMISSION": "profile must not replace isolation",
        },
        mcps=(
            {
                "name": "foo",
                "command": "foo-mcp",
                "args": ["--mode", "{{ $h }}"],
                "env": {"TOKEN": "${PROFILE_TOKEN}"},
            },
        ),
    )

    launch = build_opencode_isolation(
        profile,
        _policy(caller_arguments=("--version",), profile_arguments=("--profile",)),
        workspace,
        environment={
            "HOME": "/caller/home",
            "XDG_CONFIG_HOME": "/caller/config",
            "XDG_DATA_HOME": "/caller/data",
            "XDG_CACHE_HOME": "/caller/cache",
            "XDG_STATE_HOME": "/caller/state",
            "OPENCODE_CONFIG": "/caller/opencode.json",
            "OPENCODE_CONFIG_DIR": "/caller/opencode-config",
            "OPENCODE_CONFIG_CONTENT": "caller must not replace isolation",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "false",
            "OPENCODE_PERMISSION": "caller must not replace isolation",
        },
    )

    assert isinstance(launch, LaunchSpec)
    assert launch.executable == "opencode"
    assert launch.argv == ("opencode", "--profile", "--version")
    assert launch.environment["PROFILE_TOKEN"] == "profile-secret"
    assert launch.environment["HOME"] == str(workspace / "home")
    assert launch.environment["XDG_CONFIG_HOME"] == str(workspace / "xdg-config")
    assert launch.environment["XDG_DATA_HOME"] == str(workspace / "xdg-data")
    assert launch.environment["XDG_CACHE_HOME"] == str(workspace / "xdg-cache")
    assert launch.environment["XDG_STATE_HOME"] == str(workspace / "xdg-state")
    assert launch.environment["OPENCODE_CONFIG"] == str(workspace / "opencode.json")
    assert launch.environment["OPENCODE_CONFIG_DIR"] == str(workspace / "opencode-config")
    assert launch.environment["OPENCODE_DISABLE_PROJECT_CONFIG"] == "true"
    for name in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "OPENCODE_CONFIG_DIR",
    ):
        assert Path(launch.environment[name]).is_dir()
    assert "caller must not replace isolation" not in launch.environment["OPENCODE_CONFIG_CONTENT"]
    config = json.loads(launch.environment["OPENCODE_CONFIG_CONTENT"])
    assert config == {
        "mcp": {
            "foo": {
                "type": "local",
                "enabled": True,
                "command": ["foo-mcp", "--mode", "opencode"],
                "environment": {"TOKEN": "{env:PROFILE_TOKEN}"},
            }
        },
        "instructions": [str(prompt)],
    }
    assert (
        json.loads(Path(launch.environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8"))
        == config
    )
    assert "OPENCODE_PERMISSION" not in launch.environment
    assert "profile-secret" not in repr(launch)


def test_isolated_opencode_projects_only_permission_denials(tmp_path: Path) -> None:
    profile = _profile(
        Path("/profiles/demo"),
        settings={"permissions_deny": ("Bash(rm:*)",)},
        permissions_allow=("Read", "mcp__foo__read"),
        permissions_deny=(
            "Edit",
            "Write",
            "Read",
            "Grep",
            "Glob",
            "Bash(git status:*)",
            "mcp__foo__write",
        ),
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    launch = build_opencode_isolation(
        profile,
        _policy(),
        workspace,
        environment={"OPENCODE_PERMISSION": "caller"},
    )

    assert json.loads(launch.environment["OPENCODE_PERMISSION"]) == {
        "edit": "deny",
        "read": "deny",
        "grep": "deny",
        "glob": "deny",
        "bash": {"git status *": "deny"},
        "foo_write": "deny",
    }
    assert "allow" not in launch.environment["OPENCODE_PERMISSION"]


def test_isolated_opencode_rejects_unrepresentable_permission_denials() -> None:
    profile = _profile(Path("/profiles/demo"), permissions_deny=("NotebookEdit",))

    with pytest.raises(ProfileLaunchError, match="cannot represent deny rule"):
        build_opencode_isolation(profile, _policy(), Path.cwd(), environment={})


def test_isolated_opencode_removes_permission_environment_without_denials(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    launch = build_opencode_isolation(
        _profile(tmp_path),
        _policy(),
        workspace,
        environment={"OPENCODE_PERMISSION": "caller"},
    )

    assert "OPENCODE_PERMISSION" not in launch.environment


def test_isolated_opencode_rejects_tools_restriction_before_config_build() -> None:
    profile = _profile(Path("/profiles/demo"), tools=("read",))

    with pytest.raises(ProfileLaunchError, match="does not support tools restrictions"):
        build_opencode_isolation(profile, _policy(), Path.cwd(), environment={})


def test_isolated_opencode_rejects_enabled_plugin_restriction_before_config_build() -> None:
    profile = _profile(Path("/profiles/demo"), enabled_plugins={"demo": True})

    with pytest.raises(ProfileLaunchError, match="does not support enabled_plugins restrictions"):
        build_opencode_isolation(profile, _policy(), Path.cwd(), environment={})


@pytest.mark.parametrize(
    ("profile", "policy", "workspace"),
    [
        (
            _profile(Path("/profiles/demo"), system_prompt="relative.md"),
            _policy(),
            Path.cwd(),
        ),
        (
            _profile(Path("/profiles/demo")),
            ValidatedLaunchPolicy(
                harness="claude",
                isolated=True,
                caller_arguments=(),
                profile_arguments=(),
                warnings=(),
            ),
            Path.cwd(),
        ),
        (_profile(Path("/profiles/demo")), _policy(), Path("/does/not/exist")),
    ],
)
def test_isolated_opencode_wraps_validation_errors(
    profile: ResolvedProfile,
    policy: ValidatedLaunchPolicy,
    workspace: Path,
) -> None:
    with pytest.raises(ProfileLaunchError, match="could not build isolated OpenCode launch"):
        build_opencode_isolation(profile, policy, workspace, environment={})
