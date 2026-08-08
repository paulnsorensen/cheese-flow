"""Behavioral tests for the explicit-input Copilot renderer."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
import yaml
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.copilot import CopilotRenderer


def _profile(
    source: Path,
    *,
    isolated: bool = True,
    permissions_allow: tuple[str, ...] = ("mcp__foo__read",),
    permissions_deny: tuple[str, ...] = (),
    mcps: tuple[dict, ...] | None = None,
    agents: tuple[dict, ...] | None = None,
) -> ResolvedProfile:
    mcp_items = (
        (
            {
                "name": "foo",
                "command": "npx",
                "args": ["-y", "foo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "{{ $h }}"},
                "harnesses": ["copilot"],
                "_source_dir": str(source),
            },
        )
        if mcps is None
        else mcps
    )
    agent_items = (
        (
            {
                "name": "agent-a",
                "description": "agent description",
                "body_path": "agents/agent-a.md",
                "models": {"copilot": "sonnet"},
                "tools": ["Read", "Grep"],
                "harnesses": ["copilot"],
                "_source_dir": str(source),
            },
        )
        if agents is None
        else agents
    )
    return ResolvedProfile(
        name="demo",
        source_id="profiles/demo",
        isolated=isolated,
        permissions_allow=permissions_allow,
        permissions_deny=permissions_deny,
        mcps=mcp_items,
        agents=agent_items,
        skills=(
            {
                "name": "skill-a",
                "path": "skills/skill-a",
                "harnesses": ["copilot"],
                "_source_dir": str(source),
            },
        ),
        commands=(
            {
                "name": "command-a",
                "body_path": "commands/command-a.md",
                "harnesses": ["copilot"],
                "_source_dir": str(source),
            },
        ),
        hooks=(
            {
                "event": "sessionStart",
                "matcher": "",
                "script": "hooks/a.sh",
                "harnesses": ["copilot"],
                "_source_dir": str(source),
            },
        ),
    )


def _write_source(source: Path) -> None:
    (source / "agents").mkdir(parents=True)
    (source / "commands").mkdir(parents=True)
    (source / "hooks").mkdir(parents=True)
    (source / "skills" / "skill-a").mkdir(parents=True)
    (source / "agents" / "agent-a.md").write_text(
        "---\nname: source-name\n---\nagent body\n", encoding="utf-8"
    )
    (source / "commands" / "command-a.md").write_text("command body\n", encoding="utf-8")
    (source / "hooks" / "a.sh").write_text("#!/bin/sh\necho a\n", encoding="utf-8")
    (source / "skills" / "skill-a" / "SKILL.md").write_text("skill body\n", encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_copilot_render_is_deterministic_from_resolved_profile(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    profile = _profile(source)

    first = tmp_path / "first"
    second = tmp_path / "second"
    renderer = CopilotRenderer()
    first_paths = renderer.render(profile, first, logical_root=tmp_path / "logical")
    second_paths = renderer.render(profile, second, logical_root=tmp_path / "other-logical")

    assert _snapshot(first) == _snapshot(second)
    assert first_paths == second_paths
    assert first_paths == (
        PurePosixPath(".github/agents/agent-a.agent.md"),
        PurePosixPath(".github/skills/skill-a"),
        PurePosixPath(".github/hooks/a.sh"),
        PurePosixPath(".github/hooks/a.json"),
        PurePosixPath(".copilot/mcp-config.json"),
    )
    assert (first / ".github" / "hooks" / "a.sh").stat().st_mode & 0o111

    expected_agent = (
        "---\nname: agent-a\ndescription: agent description\n"
        "tools:\n- Read\n- Grep\n---\n\nagent body\n"
    )
    agent = (first / ".github" / "agents" / "agent-a.agent.md").read_text(encoding="utf-8")
    assert agent == expected_agent
    assert "sonnet" not in agent

    hook = json.loads((first / ".github" / "hooks" / "a.json").read_text(encoding="utf-8"))
    assert hook == {
        "event": "sessionStart",
        "matcher": "",
        "script": ".github/hooks/a.sh",
    }
    assert not (first / ".github" / "commands").exists()

    mcp = json.loads((first / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))
    assert mcp == {
        "mcpServers": {
            "foo": {
                "command": "npx",
                "args": ["-y", "foo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "copilot"},
                "tools": ["read"],
            }
        }
    }


def test_copilot_render_preserves_unowned_baseline_mcp_state(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / ".copilot").mkdir(parents=True)
    (dotfiles / ".copilot" / "mcp-config.json").write_text(
        '{"mcpServers": {"global": {"command": "must-not-load"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_DIR", str(dotfiles))
    monkeypatch.setenv("HOME", str(dotfiles / "home"))

    profile = _profile(
        source,
        mcps=(
            *_profile(source).mcps,
            {
                "name": "retired",
                "command": "retired-mcp",
                "harnesses": ["claude"],
                "_source_dir": str(source),
            },
        ),
    )
    target = tmp_path / "target"
    (target / ".copilot").mkdir(parents=True)
    (target / ".copilot" / "mcp-config.json").write_text(
        json.dumps(
            {
                "custom": {"preserve": True},
                "mcpServers": {
                    "stale": {"command": "unowned"},
                    "foo": {"command": "profile-old"},
                    "retired": {"command": "profile-retired"},
                },
            }
        ),
        encoding="utf-8",
    )

    CopilotRenderer().render(profile, target, logical_root=tmp_path / "logical")

    mcp = json.loads((target / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))
    assert mcp == {
        "custom": {"preserve": True},
        "mcpServers": {
            "stale": {"command": "unowned"},
            "foo": {
                "command": "npx",
                "args": ["-y", "foo-mcp"],
                "env": {"SERENA_MUX_HARNESS": "copilot"},
                "tools": ["read"],
            },
        },
    }
    assert json.loads((dotfiles / ".copilot" / "mcp-config.json").read_text()) == {
        "mcpServers": {"global": {"command": "must-not-load"}}
    }


def test_copilot_launch_spec_projects_profile_policy_and_snapshots_environment(
    tmp_path: Path,
) -> None:
    environment = {"TOKEN": "secret"}
    profile = _profile(
        tmp_path,
        isolated=False,
        permissions_allow=("Bash(git status:*)", "mcp__foo__*", "mcp__foo__read"),
        permissions_deny=("Bash(rm -rf:*)", "mcp__foo__write"),
    )
    spec = CopilotRenderer().launch_spec(
        profile,
        None,
        ("--prompt", "hello"),
        environment,
    )

    environment["TOKEN"] = "changed"
    assert spec.executable == "copilot"
    assert spec.argv == (
        "copilot",
        "--allow-tool=shell(git status)",
        "--allow-tool=foo",
        "--allow-tool=foo(read)",
        "--deny-tool=shell(rm -rf)",
        "--deny-tool=foo(write)",
        "--prompt",
        "hello",
    )
    assert dict(spec.environment) == {"TOKEN": "secret"}


@pytest.mark.parametrize(
    "argument",
    ("--allow-tool", "--deny-tool", "--allow-tool=caller-policy", "--deny-tool=caller-policy"),
)
def test_copilot_launch_spec_rejects_caller_policy_flags(tmp_path: Path, argument: str) -> None:
    with pytest.raises(ValueError, match="declared by the profile"):
        CopilotRenderer().launch_spec(
            _profile(tmp_path, isolated=False),
            None,
            (argument,),
            {},
        )


def test_copilot_agent_frontmatter_round_trips_yaml_scalars(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    agent = {
        "name": "agent-a",
        "description": "yes: # literal\nnext",
        "body_path": "agents/agent-a.md",
        "tools": ["Read", "yes", "null", "a: b", "#tag"],
        "metadata": {"truth": "no", "number": "123", "nested": ["on", "off"]},
        "harnesses": ["copilot"],
        "_source_dir": str(source),
    }

    target = tmp_path / "target"
    CopilotRenderer().render(
        _profile(source, isolated=False, agents=(agent,)),
        target,
        logical_root=tmp_path / "logical",
    )

    rendered = (target / ".github" / "agents" / "agent-a.agent.md").read_text(encoding="utf-8")
    _, frontmatter_and_body = rendered.split("---\n", 1)
    frontmatter, body = frontmatter_and_body.split("\n---\n\n", 1)
    assert yaml.safe_load(frontmatter) == {
        "name": "agent-a",
        "description": "yes: # literal\nnext",
        "tools": ["Read", "yes", "null", "a: b", "#tag"],
        "metadata": {"truth": "no", "number": "123", "nested": ["on", "off"]},
    }
    assert body == "agent body\n"


def test_copilot_hook_payload_projects_public_fields_and_rejects_basename_conflicts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_source(source)
    (source / "hooks" / "guard.sh").write_text("#!/bin/sh\necho first\n", encoding="utf-8")
    other_source = tmp_path / "other-source"
    (other_source / "hooks").mkdir(parents=True)
    (other_source / "hooks" / "guard.sh").write_text("#!/bin/sh\necho other\n", encoding="utf-8")

    first_hook = {
        "event": "sessionStart",
        "matcher": "",
        "script": "hooks/guard.sh",
        "harnesses": ["copilot"],
        "_source_dir": str(source),
        "_source_context": str(tmp_path / "private" / "manifest.yaml"),
        "_private_note": "must not serialize",
    }
    second_hook = {
        "event": "sessionStart",
        "matcher": "",
        "script": "hooks/guard.sh",
        "harnesses": ["copilot"],
        "_source_dir": str(other_source),
    }
    profile = _profile(source, isolated=False, agents=()).model_copy(
        update={"hooks": (first_hook, second_hook)}
    )

    with pytest.raises(ValueError, match="conflicting generated destination"):
        CopilotRenderer().render(profile, tmp_path / "conflict", logical_root=tmp_path / "logical")

    other_source.joinpath("hooks", "guard.sh").write_text(
        "#!/bin/sh\necho first\n", encoding="utf-8"
    )
    target = tmp_path / "deduped"
    CopilotRenderer().render(profile, target, logical_root=tmp_path / "logical")
    payload = json.loads((target / ".github/hooks/guard.json").read_text(encoding="utf-8"))
    assert payload == {
        "event": "sessionStart",
        "matcher": "",
        "script": ".github/hooks/guard.sh",
    }
    rendered = (target / ".github/hooks/guard.json").read_text(encoding="utf-8")
    assert "_source_context" not in rendered
    assert str(tmp_path / "private") not in rendered
