"""Behavioral tests for the explicit-root Claude renderer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.claude import ClaudeRenderer


def _profile(source: Path, *, isolated: bool = True) -> ResolvedProfile:
    return ResolvedProfile(
        name="demo",
        description="demo profile",
        source_id="profiles/demo",
        isolated=isolated,
        mcps=(
            {
                "name": "foo",
                "command": "npx",
                "args": ["-y", "foo-mcp", "{{ $h }}"],
                "env": {"SERENA_MUX_HARNESS": "{{ $h }}"},
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
        agents=(
            {
                "name": "agent-a",
                "description": "agent description",
                "body_path": "agents/agent-a.md",
                "models": {"claude": "sonnet"},
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
        skills=(
            {
                "name": "skill-a",
                "path": "skills/skill-a",
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
        commands=(
            {
                "name": "command-a",
                "description": "command description",
                "body_path": "commands/command-a.md",
                "models": {"claude": "haiku"},
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
        hooks=(
            {
                "event": "PreToolUse",
                "matcher": "Bash",
                "script": "hooks/a.sh",
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
        settings={"permissions_allow": ["Bash(git status:*)"]},
        tools=("Read", "Bash"),
        extra_args=("--verbose",),
        env={"PROFILE": "live"},
    )


def _write_source(source: Path) -> None:
    (source / "agents").mkdir(parents=True)
    (source / "commands").mkdir(parents=True)
    (source / "hooks").mkdir(parents=True)
    (source / "skills" / "skill-a").mkdir(parents=True)
    (source / "agents" / "agent-a.md").write_text("agent body\n", encoding="utf-8")
    (source / "commands" / "command-a.md").write_text("command body\n", encoding="utf-8")
    (source / "hooks" / "a.sh").write_text("#!/bin/sh\necho a\n", encoding="utf-8")
    (source / "skills" / "skill-a" / "SKILL.md").write_text("skill body\n", encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_claude_render_is_deterministic_from_explicit_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source)

    first = tmp_path / "first"
    second = tmp_path / "second"
    renderer = ClaudeRenderer()
    first_paths = renderer.render(profile, first, logical_root=tmp_path / "logical")
    second_paths = renderer.render(profile, second, logical_root=tmp_path / "other-logical")

    assert _snapshot(first) == _snapshot(second)
    assert first_paths == second_paths
    assert all(isinstance(path, PurePosixPath) for path in first_paths)
    assert (first / ".claude/plugins/local/demo/.mcp.json").is_file()
    assert (first / ".claude/plugins/local/demo/settings.json").is_file()
    assert (first / ".claude/plugins/local/demo/hooks/a.sh").stat().st_mode & 0o111
    assert json.loads((first / ".claude/plugins/local/demo/.mcp.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ]["foo"]["env"] == {"SERENA_MUX_HARNESS": "claude"}


def test_claude_render_ignores_dotfiles_and_process_discovery(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / ".claude").mkdir(parents=True)
    (dotfiles / ".claude" / "mcp.json").write_text(
        '{"mcpServers": {"global": {"command": "must-not-load"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_DIR", str(dotfiles))
    monkeypatch.setenv("HOME", str(dotfiles / "home"))

    target = tmp_path / "target"
    ClaudeRenderer().render(_profile(source), target, logical_root=tmp_path / "logical")

    servers = json.loads(
        (target / ".claude/plugins/local/demo/.mcp.json").read_text(encoding="utf-8")
    )["mcpServers"]
    assert set(servers) == {"foo"}
    global_mcp = dotfiles / ".claude" / "mcp.json"
    plugin_mcp = target / ".claude/plugins/local/demo/.mcp.json"
    assert global_mcp.read_bytes() != plugin_mcp.read_bytes()


def test_claude_launch_spec_snapshots_explicit_environment(
    tmp_path: Path,
) -> None:
    environment = {"TOKEN": "secret"}
    profile = _profile(tmp_path / "source")
    overlay = tmp_path / "overlay"

    spec = ClaudeRenderer().launch_spec(profile, overlay, ("--version",), environment)
    environment["TOKEN"] = "changed"

    assert spec.executable == "claude"
    assert spec.argv == ("claude", "--version")
    assert dict(spec.environment) == {"TOKEN": "secret"}


def test_claude_render_rejects_hook_without_execution_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source).model_copy(update={"hooks": ({"event": "Stop"},)})

    with pytest.raises(ValueError, match="neither 'script' nor 'command'"):
        ClaudeRenderer().render(profile, tmp_path / "target", logical_root=tmp_path / "logical")


def test_claude_rejects_conflicting_same_basename_hooks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    (source / "other").mkdir()
    (source / "other" / "a.sh").write_text("#!/bin/sh\necho other\n", encoding="utf-8")
    first = dict(_profile(source).hooks[0])
    second = {**first, "script": "other/a.sh"}
    profile = _profile(source).model_copy(update={"hooks": (first, second)})

    with pytest.raises(ValueError, match="conflicting generated destination"):
        ClaudeRenderer().render(profile, tmp_path / "target", logical_root=tmp_path / "logical")


def test_claude_projects_explicit_local_marketplaces_and_plugins(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source).model_copy(
        update={
            "marketplaces": {"local": str(source / "plugins")},
            "enabled_plugins": {"existing@marketplace": True},
            "native_plugins": (
                {
                    "name": "native",
                    "claude_native": True,
                    "marketplace_name": "native-market",
                    "marketplace_root": str(source / "native"),
                },
            ),
        }
    )

    target = tmp_path / "target"
    ClaudeRenderer().render(profile, target, logical_root=tmp_path / "logical")

    settings = json.loads((target / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["extraKnownMarketplaces"] == {
        "local": {"source": {"source": "directory", "path": str(source / "plugins")}},
        "native-market": {"source": {"source": "directory", "path": str(source / "native")}},
    }
    assert settings["enabledPlugins"] == {
        "existing@marketplace": True,
        "native@native-market": True,
    }


def test_claude_rejects_scalar_item_harnesses(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    profile = _profile(source).model_copy(
        update={
            "mcps": (
                {
                    "name": "wrong",
                    "command": "wrong",
                    "harnesses": "claude",
                    "_source_dir": str(source),
                },
            )
        }
    )

    with pytest.raises(ValueError, match="non-string sequences"):
        ClaudeRenderer().render(profile, tmp_path / "target", logical_root=tmp_path / "logical")
