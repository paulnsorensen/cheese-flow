"""Behavioral tests for the explicit-input Crush renderer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.models import LaunchRequest
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.crush import CrushRenderer


def _profile(source: Path, *, isolated: bool = True) -> ResolvedProfile:
    return ResolvedProfile(
        name="demo",
        source_id="profiles/demo",
        isolated=isolated,
        permissions_allow=(),
        mcps=(
            {
                "name": "stdio",
                "command": "npx",
                "args": ["-y", "demo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "{{ $h }}"},
                "disabled_tools": ["write"],
                "timeout": 15,
                "harnesses": ["crush"],
                "_source_dir": str(source),
            },
            {
                "name": "remote",
                "type": "http",
                "url": "https://example.test/mcp",
                "headers": {"Authorization": "Bearer token"},
                "harnesses": ["crush"],
                "_source_dir": str(source),
            },
        ),
        agents=(),
        skills=(),
        commands=(),
        hooks=(
            {
                "event": "PreToolUse",
                "matcher": "Bash",
                "script": "hooks/guard.sh",
                "timeout": 20,
                "harnesses": ["crush"],
                "_source_dir": str(source),
            },
            {
                "event": "SessionStart",
                "script": "hooks/ignored.sh",
                "harnesses": ["crush"],
                "_source_dir": str(source),
            },
        ),
    )


def _write_source(source: Path) -> None:
    (source / "hooks").mkdir(parents=True)
    (source / "hooks" / "guard.sh").write_text("#!/bin/sh\necho guard\n", encoding="utf-8")
    (source / "hooks" / "ignored.sh").write_text("#!/bin/sh\necho ignored\n", encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_crush_render_is_deterministic_and_uses_explicit_logical_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source)
    logical_root = tmp_path / "deployment"

    first = tmp_path / "first"
    second = tmp_path / "second"
    renderer = CrushRenderer()
    first_paths = renderer.render(profile, first, logical_root=logical_root)
    second_paths = renderer.render(profile, second, logical_root=logical_root)

    assert _snapshot(first) == _snapshot(second)
    assert first_paths == second_paths == (PurePosixPath(".config/crush/hooks/guard.sh"),)
    assert (first / ".config" / "crush" / "hooks" / "guard.sh").stat().st_mode & 0o111

    config = json.loads((first / ".config" / "crush" / "crush.json").read_text())
    assert config == {
        "mcp": {
            "stdio": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "demo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "crush"},
                "disabled_tools": ["write"],
                "timeout": 15,
            },
            "remote": {
                "type": "http",
                "url": "https://example.test/mcp",
                "headers": {"Authorization": "Bearer token"},
            },
        },
        "hooks": {
            "PreToolUse": [
                {
                    "command": str(logical_root / ".config" / "crush" / "hooks" / "guard.sh"),
                    "matcher": "Bash",
                    "timeout": 20,
                }
            ]
        },
    }


def test_crush_render_ignores_conflicting_target_state_and_dotfiles(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / ".config" / "crush").mkdir(parents=True)
    (dotfiles / ".config" / "crush" / "crush.json").write_text(
        '{"mcp": {"global": {"command": "must-not-load"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_DIR", str(dotfiles))
    monkeypatch.setenv("HOME", str(dotfiles / "home"))

    target = tmp_path / "target"
    config_path = target / ".config" / "crush" / "crush.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "mcp": {"stale": {"type": "stdio", "command": "must-not-keep"}},
                "hooks": {"PreToolUse": [{"command": "must-not-keep"}]},
            }
        ),
        encoding="utf-8",
    )

    logical_root = tmp_path / "deployment"
    CrushRenderer().render(_profile(source), target, logical_root=logical_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert set(config["mcp"]) == {"stdio", "remote"}
    assert "stale" not in config["mcp"]
    assert config["hooks"]["PreToolUse"] == [
        {
            "command": str(logical_root / ".config" / "crush" / "hooks" / "guard.sh"),
            "matcher": "Bash",
            "timeout": 20,
        }
    ]


def test_crush_render_skips_non_isolated_profiles(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    target = tmp_path / "target"

    assert (
        CrushRenderer().render(
            _profile(source, isolated=False), target, logical_root=tmp_path / "deployment"
        )
        == ()
    )
    assert not target.exists()


def test_crush_launch_spec_forwards_arguments_and_snapshots_environment(tmp_path: Path) -> None:
    environment = {"TOKEN": "secret"}
    request = LaunchRequest(
        profile_name="demo",
        source_root=tmp_path,
        harness="crush",
        arguments=("--profile", "demo"),
    )
    spec = CrushRenderer().launch_spec(
        _profile(tmp_path, isolated=False),
        None,
        request.arguments,
        environment,
    )

    environment["TOKEN"] = "changed"
    assert spec.executable == "crush"
    assert spec.argv == ("crush", "--profile", "demo")
    assert dict(spec.environment) == {"TOKEN": "secret"}


def test_crush_rejects_scalar_item_harnesses(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    profile = _profile(source).model_copy(
        update={
            "mcps": (
                {
                    "name": "wrong",
                    "command": "wrong",
                    "harnesses": "crush",
                },
            )
        }
    )

    with pytest.raises(ValueError, match="non-string sequences"):
        CrushRenderer().render(profile, tmp_path / "target", logical_root=tmp_path / "logical")


def test_crush_rejects_conflicting_hook_basename_before_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    other_source = tmp_path / "other-source"
    (other_source / "hooks").mkdir(parents=True)
    (other_source / "hooks" / "guard.sh").write_text("#!/bin/sh\necho other\n", encoding="utf-8")
    base = _profile(source)
    second_hook = {
        "event": "PreToolUse",
        "matcher": "Write",
        "script": "hooks/guard.sh",
        "harnesses": ["crush"],
        "_source_dir": str(other_source),
    }
    profile = base.model_copy(update={"hooks": (base.hooks[0], second_hook)})

    target = tmp_path / "target"
    with pytest.raises(ValueError, match="conflicting generated destination"):
        CrushRenderer().render(profile, target, logical_root=tmp_path / "logical")

    assert (target / ".config/crush/hooks/guard.sh").read_text() == "#!/bin/sh\necho guard\n"
