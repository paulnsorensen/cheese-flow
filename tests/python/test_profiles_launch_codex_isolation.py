from __future__ import annotations

import stat
import tomllib
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.codex import build_codex_isolation
from cheese_flow.profiles.launch_policy import validate_launch_policy
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile


def _profile(
    *,
    system_prompt: str | None = None,
    extra_args: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
    settings: dict[str, object] | None = None,
    permissions_allow: tuple[str, ...] = (),
    permissions_deny: tuple[str, ...] = (),
) -> ResolvedProfile:
    return ResolvedProfile(
        name="isolated",
        description="isolated Codex profile",
        source_id="profiles/isolated",
        isolated=True,
        system_prompt=system_prompt,
        tools=("read",),
        settings=settings or {},
        permissions_allow=permissions_allow,
        permissions_deny=permissions_deny,
        extra_args=extra_args,
        env=env or {},
    )


def test_isolated_codex_redirects_home_links_auth_and_projects_defaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    auth = home / ".codex" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text('{"access_token":"secret"}', encoding="utf-8")
    prompt = tmp_path / "instructions.md"
    prompt.write_text("Be concise.\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)

    profile = _profile(
        system_prompt=str(prompt),
        env={
            "CODEX_PROFILE": "isolated",
            "CODEX_HOME": str(tmp_path / "escape"),
        },
    )
    policy = validate_launch_policy(profile, "codex", ("--version",))
    spec = build_codex_isolation(
        profile,
        policy,
        workspace,
        environment={"HOME": str(home), "PATH": "/usr/bin", "EXPLICIT": "yes"},
    )

    assert isinstance(spec, LaunchSpec)
    assert spec.argv == ("codex", "--version")
    assert spec.environment["CODEX_HOME"] == str(workspace)
    assert spec.environment["CODEX_PROFILE"] == "isolated"
    assert spec.environment["EXPLICIT"] == "yes"

    auth_link = workspace / "auth.json"
    assert auth_link.is_symlink()
    assert auth_link.resolve() == auth
    config_path = workspace / "config.toml"
    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["approval_policy"] == "on-request"
    assert config["approvals_reviewer"] == "auto_review"
    assert config["sandbox_mode"] == "workspace-write"
    assert config["model_instructions_file"] == str(prompt)
    assert config["tui"]["input_mode"] == "vim"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert policy.warnings == ()


def test_isolated_codex_uses_launch_permission_channel(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    profile = _profile(
        settings={"permissions_deny": ("Bash(rm:*)",)},
        permissions_deny=("Bash(git status:*)",),
    )
    policy = validate_launch_policy(profile, "codex", ())

    build_codex_isolation(profile, policy, workspace, environment={"HOME": str(tmp_path)})

    rules = (workspace / "rules" / "cheese-flow-canonical.rules").read_text(encoding="utf-8")
    assert '"git"' in rules
    assert '"rm"' not in rules


def test_isolated_codex_rejects_a_non_codex_policy_before_projection(tmp_path: Path) -> None:
    profile = _profile()
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    policy = validate_launch_policy(profile, "claude", ())

    with pytest.raises(ProfileLaunchError, match="isolated Codex"):
        build_codex_isolation(profile, policy, workspace, environment={"HOME": str(tmp_path)})


def test_isolated_codex_skips_missing_authentication_without_ambient_home(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    profile = _profile()
    policy = validate_launch_policy(profile, "codex", ())

    spec = build_codex_isolation(profile, policy, workspace, environment={"PATH": "/usr/bin"})

    assert spec.environment["CODEX_HOME"] == str(workspace)
    assert not (workspace / "auth.json").exists()
