from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.claude import build_claude_isolation
from cheese_flow.profiles.launch_policy import ValidatedLaunchPolicy
from cheese_flow.profiles.parse import ResolvedProfile


def _policy(*, caller: tuple[str, ...] = ()) -> ValidatedLaunchPolicy:
    return ValidatedLaunchPolicy(
        harness="claude",
        isolated=True,
        caller_arguments=caller,
        profile_arguments=("--profile-flag",),
        warnings=(),
    )


def test_isolated_claude_builds_closed_world_inputs(tmp_path: Path) -> None:
    source = tmp_path / "profile"
    source.mkdir()
    (source / "CLAUDE.md").write_text("Profile instructions\n", encoding="utf-8")
    skill = source / "skills" / "todo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Use todo\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    profile = ResolvedProfile(
        name="todo",
        source_id="profiles/todo",
        isolated=True,
        system_prompt="CLAUDE.md",
        tools=("Read", "Skill", "mcp__todoist__*"),
        permissions_allow=("mcp__todoist__*",),
        permissions_deny=("Edit",),
        enabled_plugins={"plugin-dev@claude-plugins-official": True},
        env={"PROFILE_TOKEN": "secret"},
        extra_args=("--profile-flag",),
        mcps=(
            {
                "name": "todoist",
                "command": "npx",
                "args": ("-y", "todoist-mcp"),
                "env": {"TOKEN": '{{ env "PROFILE_TOKEN" }}'},
                "_source_dir": str(source),
            },
        ),
        skills=({"name": "todo", "path": "skills/todo", "_source_dir": str(source)},),
    )

    spec = build_claude_isolation(
        profile,
        _policy(caller=("--resume",)),
        workspace,
        environment={"HOME": "/explicit/home", "PROFILE_TOKEN": "caller"},
    )

    assert spec.executable == "claude"
    assert spec.argv[1] == "--bare"
    assert spec.argv[0] == "claude"
    assert spec.argv[-2:] == ("--profile-flag", "--resume")
    assert spec.environment == {
        "HOME": "/explicit/home",
        "PROFILE_TOKEN": "secret",
    }

    mcp_path = Path(spec.argv[spec.argv.index("--mcp-config") + 1])
    assert json.loads(mcp_path.read_text(encoding="utf-8")) == {
        "mcpServers": {
            "todoist": {
                "command": "npx",
                "args": ["-y", "todoist-mcp"],
                "env": {"TOKEN": "secret"},
            }
        }
    }

    assert spec.argv[spec.argv.index("--setting-sources") + 1] == ""
    assert spec.argv[spec.argv.index("--tools") + 1] == "Read,Skill,mcp__todoist__*"
    prompt_path = Path(spec.argv[spec.argv.index("--append-system-prompt-file") + 1])
    assert prompt_path == source / "CLAUDE.md"
    settings_path = Path(spec.argv[spec.argv.index("--settings") + 1])
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "permissions": {"allow": ["mcp__todoist__*"], "deny": ["Edit"]},
        "enabledPlugins": {"plugin-dev@claude-plugins-official": True},
    }
    plugin_dir = Path(spec.argv[spec.argv.index("--plugin-dir") + 1])
    assert (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    assert (plugin_dir / "skills" / "todo" / "SKILL.md").read_text(encoding="utf-8") == "Use todo\n"


def test_isolated_claude_rejects_missing_mcp_template_environment(
    tmp_path: Path,
) -> None:
    profile = ResolvedProfile(
        name="missing-env",
        source_id="profiles/missing-env",
        isolated=True,
        env={},
        mcps=(
            {
                "name": "secret",
                "command": "secret-mcp",
                "args": ('{{ env "PROFILE_TOKEN" }}',),
            },
        ),
    )

    with pytest.raises(ProfileLaunchError, match="isolated Claude launch"):
        build_claude_isolation(
            profile,
            _policy(),
            tmp_path / "workspace",
            environment={},
        )


def test_isolated_claude_builder_rejects_invalid_inputs_before_launch(tmp_path: Path) -> None:
    profile = ResolvedProfile(name="broken", source_id="profiles/broken", isolated=True)
    with pytest.raises(ProfileLaunchError, match="isolated Claude launch"):
        build_claude_isolation(
            profile,
            _policy(),
            tmp_path / "missing-workspace",
            environment={},
        )
