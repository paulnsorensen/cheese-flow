"""Behavioral tests for the explicit-root Cursor renderer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.cursor import CursorRenderer


def _profile(source: Path, *, isolated: bool = True) -> ResolvedProfile:
    return ResolvedProfile(
        name="demo",
        source_id="profiles/demo",
        isolated=isolated,
        mcps=(
            {
                "name": "foo",
                "command": "npx",
                "args": ["-y", "foo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "{{ $h }}"},
                "harnesses": ["cursor"],
            },
        ),
        agents=(
            {
                "name": "agent-a",
                "description": "agent description",
                "body_path": "agents/agent-a.md",
                "models": {"cursor": "sonnet"},
                "harnesses": ["cursor"],
                "_source_dir": str(source),
            },
        ),
        skills=(
            {
                "name": "skill-a",
                "path": "skills/skill-a",
                "harnesses": ["cursor"],
                "_source_dir": str(source),
            },
        ),
        commands=(
            {
                "name": "command-a",
                "description": "command description",
                "body_path": "commands/command-a.md",
                "models": {"cursor": "haiku"},
                "harnesses": ["cursor"],
                "_source_dir": str(source),
            },
        ),
        hooks=(
            {
                "event": "beforeShellExecution",
                "matcher": "",
                "script": "hooks/a.sh",
                "harnesses": ["cursor"],
                "_source_dir": str(source),
            },
        ),
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


def test_cursor_render_is_deterministic_from_explicit_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source)

    first = tmp_path / "first"
    second = tmp_path / "second"
    renderer = CursorRenderer()
    first_paths = renderer.render(profile, first, logical_root=tmp_path / "logical")
    second_paths = renderer.render(profile, second, logical_root=tmp_path / "other-logical")

    assert _snapshot(first) == _snapshot(second)
    assert first_paths == second_paths
    assert first_paths == (
        PurePosixPath(".cursor/mcp.json"),
        PurePosixPath(".claude/agents/agent-a.md"),
        PurePosixPath(".cursor/agents/agent-a.md"),
        PurePosixPath(".agents/skills/skill-a"),
        PurePosixPath(".cursor/commands/command-a.md"),
        PurePosixPath(".cursor/hooks/a.sh"),
        PurePosixPath(".cursor/hooks.json"),
    )
    assert (first / ".cursor" / "hooks" / "a.sh").stat().st_mode & 0o111
    mcp = json.loads((first / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["foo"] == {
        "command": "npx",
        "args": ["-y", "foo-mcp"],
        "env": {"SERENA_MUX_HARNESS": "cursor"},
    }


def test_cursor_render_uses_target_not_dotfiles_state(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / ".cursor").mkdir(parents=True)
    (dotfiles / ".cursor" / "mcp.json").write_text(
        '{"mcpServers": {"global": {"command": "must-not-load"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_DIR", str(dotfiles))
    monkeypatch.setenv("HOME", str(dotfiles / "home"))

    target = tmp_path / "target"
    CursorRenderer().render(_profile(source), target, logical_root=tmp_path / "logical")

    mcp = json.loads((target / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert set(mcp["mcpServers"]) == {"foo"}
    assert "global" not in mcp["mcpServers"]
    assert (dotfiles / ".cursor" / "mcp.json").read_text(encoding="utf-8") == (
        '{"mcpServers": {"global": {"command": "must-not-load"}}}'
    )


def test_cursor_launch_spec_is_a_plain_explicit_exec_projection() -> None:
    environment = {"TOKEN": "secret"}
    spec = CursorRenderer().launch_spec(
        _profile(Path("/profiles"), isolated=False),
        None,
        ("--version",),
        environment,
    )

    environment["TOKEN"] = "changed"
    assert spec.executable == "cursor"
    assert spec.argv == ("cursor", "--version")
    assert dict(spec.environment) == {"TOKEN": "secret"}


def test_cursor_rejects_scalar_item_harnesses(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    profile = _profile(source).model_copy(
        update={
            "mcps": (
                {
                    "name": "wrong",
                    "command": "wrong",
                    "harnesses": "nocursor",
                },
            )
        }
    )

    with pytest.raises(ValueError, match="non-string sequences"):
        CursorRenderer().render(profile, tmp_path / "target", logical_root=tmp_path / "logical")
