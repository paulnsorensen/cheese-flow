"""Behavioral tests for the explicit-root OpenCode renderer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.opencode import OpencodeRenderer


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
                "env": {
                    "SERENA_MUX_HARNESS": "{{ $h }}",
                    "TOKEN": "${TOKEN}",
                },
                "harnesses": ["opencode"],
                "_source_dir": str(source),
            },
        ),
        agents=(
            {
                "name": "reader",
                "description": "read-only agent",
                "body_path": "agents/reader.md",
                "models": {"opencode": "local-coder"},
                "tools": ["Read"],
                "harnesses": ["opencode"],
                "_source_dir": str(source),
            },
        ),
        skills=(
            {
                "name": "skill-a",
                "path": "skills/skill-a",
                "harnesses": ["opencode"],
                "_source_dir": str(source),
            },
        ),
        settings={
            "permissions_allow": ["Bash(git status:*)", "Read(*)"],
            "permissions_deny": ["Bash(git status:*)"],
        },
        env={"TOKEN": "secret"},
    )


def _write_source(source: Path) -> None:
    (source / "agents").mkdir(parents=True)
    (source / "skills" / "skill-a").mkdir(parents=True)
    (source / "agents" / "reader.md").write_text(
        "---\nname: stale\n---\nreader body\n", encoding="utf-8"
    )
    (source / "skills" / "skill-a" / "SKILL.md").write_text("skill body\n", encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_opencode_render_is_deterministic_from_explicit_profile_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source)

    first = tmp_path / "first"
    second = tmp_path / "second"
    renderer = OpencodeRenderer()
    first_paths = renderer.render(profile, first, logical_root=tmp_path / "logical")
    second_paths = renderer.render(profile, second, logical_root=tmp_path / "other-logical")

    assert _snapshot(first) == _snapshot(second)
    assert first_paths == second_paths
    assert first_paths == (
        PurePosixPath("agents/reader.md"),
        PurePosixPath("opencode.json"),
        PurePosixPath("skills/skill-a/SKILL.md"),
    )
    assert json.loads((first / "opencode.json").read_text(encoding="utf-8")) == {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "foo": {
                "type": "local",
                "enabled": True,
                "command": ["npx", "-y", "foo-mcp", "opencode"],
                "environment": {
                    "SERENA_MUX_HARNESS": "opencode",
                    "TOKEN": "{env:TOKEN}",
                },
            }
        },
        "permission": {
            "bash": {"git status *": "deny"},
            "read": {"*": "allow"},
        },
    }
    assert (first / "agents/reader.md").read_text(encoding="utf-8") == (
        "---\ndescription: read-only agent\nmode: subagent\n"
        "model: local-coder\npermission:\n  edit: deny\n---\nreader body\n"
    )


def test_opencode_compile_uses_persistent_permission_channel(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    base = _profile(source)
    profile = base.model_copy(
        update={
            "settings": {"permissions_deny": ("Bash(rm:*)",)},
            "permissions_deny": ("Bash(git status:*)",),
        }
    )
    target = tmp_path / "target"

    OpencodeRenderer().render(profile, target, logical_root=tmp_path / "logical")

    permission = json.loads((target / "opencode.json").read_text())["permission"]
    assert permission == {"bash": {"rm *": "deny"}}


def test_opencode_render_does_not_discover_dotfiles_or_installation_state(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    decoy = tmp_path / "dotfiles"
    (decoy / "cache" / "opencode").mkdir(parents=True)
    (decoy / "vault").mkdir()
    (decoy / "opencode.json").write_text(
        '{"mcp": {"decoy": {"command": "must-not-load"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(decoy))
    monkeypatch.setenv("DOTFILES_DIR", str(decoy))

    target = tmp_path / "target"
    OpencodeRenderer().render(_profile(source), target, logical_root=tmp_path / "logical")

    config = json.loads((target / "opencode.json").read_text(encoding="utf-8"))
    assert set(config["mcp"]) == {"foo"}
    assert "decoy" not in config["mcp"]
    assert not (target / "cache").exists()
    assert not (target / "vault").exists()


def test_opencode_non_isolated_render_leaves_shared_config_unmanaged(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    target = tmp_path / "target"

    written = OpencodeRenderer().render(
        _profile(source, isolated=False), target, logical_root=tmp_path / "logical"
    )

    assert written == (
        PurePosixPath("agents/reader.md"),
        PurePosixPath("skills/skill-a/SKILL.md"),
    )
    assert not (target / "opencode.json").exists()


def test_opencode_launch_spec_snapshots_explicit_environment(tmp_path: Path) -> None:
    environment = {"TOKEN": "secret"}
    launch = OpencodeRenderer().launch_spec(
        _profile(tmp_path / "source"),
        tmp_path / "overlay",
        ("--version", "prompt"),
        environment,
    )
    environment["TOKEN"] = "changed"

    assert isinstance(launch, LaunchSpec)
    assert launch.executable == "opencode"
    assert launch.argv == ("opencode", "--version", "prompt")
    assert dict(launch.environment) == {"TOKEN": "secret"}


def test_opencode_rejects_remote_mcp_before_writing_anything(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    base = _profile(source)
    profile = base.model_copy(
        update={
            "mcps": (
                {
                    **dict(base.mcps[0]),
                    "type": "http",
                    "url": "https://example.test/mcp",
                },
            )
        }
    )
    target = tmp_path / "target"

    with pytest.raises(ValueError, match="does not support remote transports"):
        OpencodeRenderer().render(profile, target, logical_root=tmp_path / "logical")

    assert not target.exists()
