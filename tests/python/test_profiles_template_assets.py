"""Behavioral tests for deterministic profile rendering helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.rendering.agents import (
    agent_is_read_only,
    claude_agent_frontmatter,
    strip_frontmatter,
    write_shared_claude_agent,
)
from cheese_flow.profiles.rendering.assets import (
    body_abs,
    copy_hook_shared_assets,
    shared_asset_relpath,
)
from cheese_flow.profiles.rendering.template import (
    render_mcp_for_harness,
    render_value,
)


def test_template_rendering_is_deterministic_and_does_not_mutate_input() -> None:
    template = '{{ if eq $h "claude" }}claude-code{{ else }}{{ $h }}{{ end }}'
    mcp = {
        "name": "example",
        "command": "example-mcp",
        "args": [template],
        "env": {"PROFILE": '{{ env "PROFILE" }}'},
    }
    environment = {"PROFILE": "live"}

    first = render_mcp_for_harness(mcp, "codex", environment=environment)
    second = render_mcp_for_harness(mcp, "codex", environment=environment)

    assert (
        first
        == second
        == {
            "name": "example",
            "command": "example-mcp",
            "args": ["codex"],
            "env": {"PROFILE": "live"},
        }
    )
    assert mcp["args"] == [template]
    assert mcp["env"] == {"PROFILE": '{{ env "PROFILE" }}'}


def test_render_value_uses_explicit_environment_only() -> None:
    assert render_value('{{ env "PROFILE" }}', "codex", environment={"PROFILE": "plan"}) == "plan"
    assert render_value("${PROFILE}", "codex", environment={"PROFILE": "plan"}) == "${PROFILE}"


def test_conditional_assignments_render_only_the_selected_branch() -> None:
    template = (
        '{{ if eq $h "claude" }}{{ $value := "selected" }}'
        '{{ else }}{{ $value := "unselected" }}{{ end }}{{ $value }}'
    )

    assert render_value(template, "claude") == "selected"
    assert render_value(template, "codex") == "unselected"


def test_conditional_condition_uses_pre_branch_state() -> None:
    template = (
        '{{ if eq $value "selected" }}selected'
        '{{ else }}{{ $value := "selected" }}unselected{{ end }}'
    )

    assert render_value(template, "codex") == "unselected"


def test_nested_conditionals_preserve_selected_assignments() -> None:
    template = (
        '{{ if eq $h "claude" }}'
        '{{ if eq $h "claude" }}{{ $value := "inner-selected" }}'
        '{{ else }}{{ $value := "inner-unselected" }}{{ end }}'
        "{{ $value }}"
        '{{ else }}{{ $value := "outer-unselected" }}{{ end }}'
        "{{ $value }}"
    )

    assert render_value(template, "claude") == "inner-selectedinner-selected"
    assert render_value(template, "codex") == "outer-unselected"


def test_strip_frontmatter_only_removes_a_closed_leading_block() -> None:
    assert strip_frontmatter("---\na: 1\n---\nbody\n") == "body\n"
    body = "body\n---\nlater\n"
    assert strip_frontmatter(body) == body
    unterminated = "---\na: 1\n"
    assert strip_frontmatter(unterminated) == unterminated


def test_agent_frontmatter_and_read_only_predicate_include_mcp_writers() -> None:
    item = {
        "name": "reviewer",
        "description": "Reviews changes",
        "tools": ["Read", "Grep"],
        "disallowedTools": [
            "Edit",
            "Write",
            "MultiEdit",
            "NotebookEdit",
            "mcp__tilth__tilth_write",
        ],
        "models": {"claude": "sonnet"},
        "color": "green",
        "effort": "high",
        "maxTurns": 10,
        "skills": ["age"],
    }
    assert agent_is_read_only(item)
    assert not agent_is_read_only({"tools": ["Read", "mcp__tilth__tilth_write"]})
    assert not agent_is_read_only({"tools": ["Read", "mcp__tilth__*"]})
    assert claude_agent_frontmatter(item) == {
        "name": "reviewer",
        "description": "Reviews changes",
        "tools": "Read, Grep",
        "disallowedTools": "[Edit, Write, MultiEdit, NotebookEdit, mcp__tilth__tilth_write]",
        "model": "sonnet",
        "color": "green",
        "effort": "high",
        "maxTurns": "10",
        "skills": "[age]",
    }


def test_asset_and_body_helpers_use_explicit_paths(tmp_path: Path) -> None:
    assert shared_asset_relpath("agents/lib/sub/example.sh") == "lib/sub/example.sh"
    assert shared_asset_relpath("example.sh") == "example.sh"
    with pytest.raises(ValueError):
        shared_asset_relpath("../outside.sh")

    source = tmp_path / "source"
    source.mkdir()
    body = source / "agents" / "reviewer.md"
    body.parent.mkdir()
    body.write_text("body\n")
    asset = source / "agents" / "lib" / "helper.sh"
    asset.parent.mkdir()
    asset.write_text("helper\n")
    item = {"body_path": "agents/reviewer.md", "_source_dir": source}
    assert body_abs(item) == body

    target = tmp_path / "target"
    written: list[str] = []
    copy_hook_shared_assets(
        {"_source_dir": source, "shared_assets": ["agents/lib/helper.sh"]},
        target / ".codex",
        target,
        written,
    )
    assert (target / ".codex/lib/helper.sh").read_text() == "helper\n"
    assert written == [".codex/lib/helper.sh"]


def test_shared_assets_dedupe_only_when_bytes_and_mode_match(tmp_path: Path) -> None:
    sources = []
    for index, mode in enumerate((0o640, 0o640, 0o600)):
        source = tmp_path / f"source-{index}"
        asset = source / "agents" / "lib" / "helper.sh"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"helper\n")
        asset.chmod(mode)
        sources.append(source)

    target = tmp_path / "target"
    written: list[str] = []
    claims: dict[str, tuple[bytes, int]] = {}
    for source in sources[:2]:
        copy_hook_shared_assets(
            {"_source_dir": source, "shared_assets": ["agents/lib/helper.sh"]},
            target / ".codex",
            target,
            written,
            claims=claims,
        )

    destination = target / ".codex/lib/helper.sh"
    assert destination.read_bytes() == b"helper\n"
    assert destination.stat().st_mode & 0o777 == 0o640
    assert written == [".codex/lib/helper.sh"]
    with pytest.raises(ValueError, match="conflicting generated destination"):
        copy_hook_shared_assets(
            {"_source_dir": sources[2], "shared_assets": ["agents/lib/helper.sh"]},
            target / ".codex",
            target,
            written,
            claims=claims,
        )


def test_shared_agent_frontmatter_serializes_scalar_looking_strings_as_strings(
    tmp_path: Path,
) -> None:
    body = tmp_path / "agent.md"
    body.write_text("body\n", encoding="utf-8")
    target = tmp_path / "target"
    written: list[str] = []

    write_shared_claude_agent(
        target,
        "agent",
        body,
        {
            "description": "[looks: like a list]",
            "model": "true",
            "custom": "colon: value",
            "multiline": "first line\nsecond line",
        },
        written,
    )

    rendered = (target / ".claude/agents/agent.md").read_text(encoding="utf-8")
    metadata, body_text = rendered.split("---\n", 2)[1:]
    assert yaml.safe_load(metadata) == {
        "description": "[looks: like a list]",
        "model": "true",
        "custom": "colon: value",
        "multiline": "first line\nsecond line",
    }
    assert body_text == "body\n"


def test_frozen_profile_mcp_templates_are_json_ready_and_missing_env_fails() -> None:
    profile = ResolvedProfile(
        name="frozen",
        source_id="profiles/frozen",
        env={"TOKEN": "secret"},
        mcps=(
            {
                "name": "example",
                "command": "example-mcp",
                "args": ('{{ env "TOKEN" }}', ("{{ $h }}",)),
                "env": {"TOKEN": '{{ env "TOKEN" }}'},
            },
        ),
    )

    rendered = render_mcp_for_harness(profile.mcps[0], "cursor", environment=profile.env)

    assert rendered == {
        "name": "example",
        "command": "example-mcp",
        "args": ["secret", ["cursor"]],
        "env": {"TOKEN": "secret"},
    }
    assert isinstance(profile.mcps[0]["args"], tuple)
    with pytest.raises(ValueError, match="TOKEN"):
        render_mcp_for_harness(profile.mcps[0], "cursor", environment={})
