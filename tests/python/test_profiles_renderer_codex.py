from __future__ import annotations

import json
import tomllib
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.renderers.codex import CodexRenderer
from cheese_flow.profiles.source import ResolvedProfile


def _profile(source: Path) -> ResolvedProfile:
    (source / "reader.md").write_text("reader instructions\n")
    (source / "writer.md").write_text("writer instructions\n")
    (source / "hook.sh").write_text("#!/bin/sh\nprintf hook\n")
    return ResolvedProfile(
        name="sample",
        source_id="profiles/sample",
        agents=(
            {
                "name": "reader",
                "description": "Read-only agent",
                "body_path": "reader.md",
                "tools": ("Read", "mcp__tilth__tilth_read"),
                "_source_dir": source,
            },
            {
                "name": "writer",
                "description": "Write-capable agent",
                "body_path": "writer.md",
                "tools": ("Read", "mcp__tilth__tilth_write"),
                "_source_dir": source,
            },
        ),
        hooks=(
            {
                "name": "sample-hook",
                "event": "PreToolUse",
                "script": "hook.sh",
                "harnesses": ("codex",),
                "_source_dir": source,
            },
        ),
    )


def test_codex_preserves_read_only_decision_for_mcp_tools(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    profile = _profile(source)

    written = CodexRenderer().render(profile, target, logical_root=target)

    assert written[:2] == (
        PurePosixPath(".codex/agents/reader.toml"),
        PurePosixPath(".codex/agents/writer.toml"),
    )
    assert all(isinstance(path, PurePosixPath) for path in written)
    reader = tomllib.loads((target / ".codex/agents/reader.toml").read_text())
    writer = tomllib.loads((target / ".codex/agents/writer.toml").read_text())
    assert reader["sandbox_mode"] == "read-only"
    assert "sandbox_mode" not in writer


def test_codex_render_is_deterministic_from_explicit_roots(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    profile = _profile(source)
    logical_root = tmp_path / "logical-root"
    first = tmp_path / "first"
    second = tmp_path / "second"
    (tmp_path / "unrelated-cwd").mkdir()
    monkeypatch.chdir(tmp_path / "unrelated-cwd")
    monkeypatch.setenv("CHEESE_FLOW_PROFILE_ROOT", str(tmp_path / "wrong-root"))

    first_written = CodexRenderer().render(profile, first, logical_root=logical_root)
    second_written = CodexRenderer().render(profile, second, logical_root=logical_root)

    assert first_written == second_written
    assert first_written[-1] == PurePosixPath(".codex/hooks.json")
    for relative in first_written:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()
    hooks = json.loads((first / ".codex/hooks.json").read_text())
    command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command == f"bash {logical_root / '.codex/hooks/hook.sh'}"


def test_codex_compile_uses_persistent_permission_channel(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    base = _profile(source)
    profile = base.model_copy(
        update={
            "settings": {"permissions_deny": ("Bash(rm:*)",)},
        }
    )
    target = tmp_path / "target"

    CodexRenderer().render(profile, target, logical_root=target)

    rules = (target / ".codex" / "rules" / "cheese-flow-canonical.rules").read_text()
    assert '"rm"' in rules
    assert '"git"' not in rules


def test_codex_launch_spec_is_a_pure_base_projection(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    profile = _profile(source)
    environment = {"CODEX_PROFILE": "sample", "PATH": "/bin"}

    launch = CodexRenderer().launch_spec(
        profile,
        tmp_path / "overlay",
        ("--quiet", "prompt"),
        environment,
    )

    assert isinstance(launch, LaunchSpec)
    assert launch.executable == "codex"
    assert launch.argv == ("codex", "--quiet", "prompt")
    assert dict(launch.environment) == environment


def test_codex_rejects_conflicting_hook_basename_before_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first_profile = _profile(source)
    other_source = tmp_path / "other-source"
    other_source.mkdir()
    (other_source / "reader.md").write_text("reader instructions\n")
    (other_source / "writer.md").write_text("writer instructions\n")
    (other_source / "hook.sh").write_text("#!/bin/sh\nprintf other\n")
    second_hook = {
        "name": "other-hook",
        "event": "PreToolUse",
        "script": "hook.sh",
        "harnesses": ("codex",),
        "_source_dir": other_source,
    }
    profile = first_profile.model_copy(update={"hooks": (first_profile.hooks[0], second_hook)})

    target = tmp_path / "target"
    with pytest.raises(ValueError, match="conflicting generated destination"):
        CodexRenderer().render(profile, target, logical_root=target)

    assert (target / ".codex/hooks/hook.sh").read_text() == "#!/bin/sh\nprintf hook\n"
