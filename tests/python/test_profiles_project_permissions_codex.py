from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfilePermissionsError
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.project_permissions_codex import plan_project_permissions
from cheese_flow.profiles.rendering.permissions import render_codex_rules_file


def _profile(
    *,
    allow: tuple[str, ...] = (),
    deny: tuple[str, ...] = (),
    settings: dict[str, object] | None = None,
) -> ResolvedProfile:
    return ResolvedProfile(
        name="project-permissions",
        source_id="profiles/project-permissions",
        permissions_allow=allow,
        permissions_deny=deny,
        settings=settings or {},
    )


def _planned_map(planned: tuple[tuple[Path, bytes], ...]) -> dict[Path, bytes]:
    return dict(planned)


def test_local_mode_has_no_codex_personal_layer(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "user-owned"\n', encoding="utf-8")

    planned = plan_project_permissions(
        _profile(allow=("Bash(git:*)",)),
        tmp_path,
        local=True,
    )

    assert planned == ()
    assert config.read_text(encoding="utf-8") == 'model = "user-owned"\n'


def test_committed_bash_rules_plan_uses_only_codex_rules_surface(tmp_path: Path) -> None:
    planned = plan_project_permissions(
        _profile(allow=("Bash(git:*)",), deny=("Bash(sudo:*)",)),
        tmp_path,
        local=False,
    )

    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    expected = (
        "# Managed by cheese-flow — canonical cross-harness permission rules.\n"
        "# Do not edit; regenerated on every profile compilation. "
        "The Codex-owned default.rules is untouched.\n"
        "\n"
        'prefix_rule(\n    pattern = ["git"],\n    decision = "allow",\n)\n'
        'prefix_rule(\n    pattern = ["sudo"],\n    decision = "forbidden",\n)\n'
    )

    assert expected == render_codex_rules_file(((("git",), "allow"), (("sudo",), "forbidden")))

    assert planned == ((rules_path, expected.encode("utf-8")),)
    assert not rules_path.exists()
    assert not (tmp_path / ".codex" / "config.toml").exists()


def test_bash_profile_transition_reconciles_canonical_rules_to_empty(
    tmp_path: Path,
) -> None:
    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    first = _planned_map(
        plan_project_permissions(
            _profile(allow=("Bash(git:*)",)),
            tmp_path,
            local=False,
        )
    )
    second = _planned_map(
        plan_project_permissions(
            _profile(),
            tmp_path,
            local=False,
        )
    )

    assert b'"git"' in first[rules_path]
    assert second[rules_path] == render_codex_rules_file(()).encode("utf-8")
    assert b'"git"' not in second[rules_path]


def test_committed_mcp_plan_preserves_unrelated_config_and_uses_settings_fallback(
    tmp_path: Path,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    original = (
        '# user-owned config\nmodel = "o4-mini"\n\n[mcp_servers.user]\ncommand = "user-mcp"\n'
    )
    config.write_text(original, encoding="utf-8")

    planned = plan_project_permissions(
        _profile(settings={"permissions_allow": ["mcp__tilth__tilth_read"]}),
        tmp_path,
        local=False,
    )

    assert config.read_text(encoding="utf-8") == original
    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    assert tuple(path for path, _ in planned) == (rules_path, config)
    rendered = tomllib.loads(_planned_map(planned)[config].decode("utf-8"))
    assert rendered == {
        "model": "o4-mini",
        "mcp_servers": {
            "user": {"command": "user-mcp"},
            "tilth": {"enabled_tools": ["tilth_read"]},
        },
    }


def test_mcp_allow_and_deny_scopes_share_one_server_entry(tmp_path: Path) -> None:
    planned = plan_project_permissions(
        _profile(
            allow=("mcp__tilth__tilth_read",),
            deny=("mcp__tilth__tilth_write",),
        ),
        tmp_path,
        local=False,
    )

    config = tmp_path / ".codex" / "config.toml"
    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    assert tuple(path for path, _ in planned) == (rules_path, config)
    rendered = tomllib.loads(_planned_map(planned)[config].decode("utf-8"))
    assert rendered["mcp_servers"]["tilth"] == {
        "enabled_tools": ["tilth_read"],
        "disabled_tools": ["tilth_write"],
    }


def test_whole_server_allow_drops_named_enabled_tools_but_keeps_denies(
    tmp_path: Path,
) -> None:
    planned = plan_project_permissions(
        _profile(
            allow=("mcp__tilth__*", "mcp__tilth__tilth_read"),
            deny=("mcp__tilth__tilth_write",),
        ),
        tmp_path,
        local=False,
    )

    config = tmp_path / ".codex" / "config.toml"
    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    assert tuple(path for path, _ in planned) == (rules_path, config)
    rendered = tomllib.loads(_planned_map(planned)[config].decode("utf-8"))
    assert rendered["mcp_servers"]["tilth"] == {
        "disabled_tools": ["tilth_write"],
    }


def test_non_bash_non_mcp_rules_plan_empty_canonical_rules(tmp_path: Path) -> None:
    planned = plan_project_permissions(_profile(allow=("Read",)), tmp_path, local=False)

    rules_path = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    assert planned == ((rules_path, render_codex_rules_file(()).encode("utf-8")),)
    assert not rules_path.exists()
    assert not (tmp_path / ".codex").exists()


def test_invalid_permission_rules_fail_before_planning(tmp_path: Path) -> None:
    with pytest.raises(ProfilePermissionsError, match="Bash rules"):
        plan_project_permissions(
            _profile(allow=("Bash(git)",)),
            tmp_path,
            local=False,
        )

    assert not (tmp_path / ".codex").exists()
