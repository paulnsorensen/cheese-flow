"""Port of `tests/compiler.test.ts` plus the US-004 byte-parity snapshot.

The byte-parity snapshot fixture is the regression gate: ``basic-agent.md``
and ``basic-skill/SKILL.md`` rendered for ``claude-code`` must match the
checked-in fixtures byte-for-byte. Fixtures were captured from the TS
pipeline at the cutover boundary so future drift is impossible to miss.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from textwrap import dedent

import pytest
from cheese_flow.lib.compiler import (
    compile_harness_bundle,
    compile_harness_bundles,
    preview_agent,
    read_skill,
)
from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.schemas import (
    HarnessModel,
    parse_agent_frontmatter,
    parse_skill_frontmatter,
    resolve_model,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "byte_parity"


def _stage_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    shutil.copytree(REPO_ROOT / "agents", project_root / "agents")
    shutil.copytree(REPO_ROOT / "skills", project_root / "skills")
    return project_root


def test_byte_parity_snapshot_basic_agent_claude_code(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    actual = (project_root / ".claude" / "agents" / "basic-agent.md").read_text(
        encoding="utf-8"
    )
    expected = (FIXTURE_DIR / "basic-agent.claude-code.md").read_text(
        encoding="utf-8"
    )
    assert actual == expected, "basic-agent.md drifted from the byte-parity fixture"


def test_byte_parity_snapshot_basic_skill_claude_code(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    actual = (
        project_root / ".claude" / "skills" / "basic-skill" / "SKILL.md"
    ).read_text(encoding="utf-8")
    expected = (FIXTURE_DIR / "basic-skill.claude-code.md").read_text(
        encoding="utf-8"
    )
    assert actual == expected, "basic-skill SKILL.md drifted from the byte-parity fixture"


def test_compiles_basic_agent_template_for_claude_code_and_codex(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    outputs = asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code", "codex"]
        )
    )
    assert len(outputs) == 2

    claude_agent = (
        project_root / ".claude" / "agents" / "basic-agent.md"
    ).read_text(encoding="utf-8")
    codex_agent = (
        project_root / ".codex" / "agents" / "basic-agent.md"
    ).read_text(encoding="utf-8")

    claude_data, _ = parse_frontmatter(claude_agent)
    codex_data, _ = parse_frontmatter(codex_agent)
    assert claude_data["model"] == "sonnet"
    assert codex_data["model"] == "gpt-5-codex"

    claude_plugin = json.loads(
        (project_root / ".claude" / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert claude_plugin["name"] == "cheese-flow"
    assert claude_plugin["agents"] == "./agents/"
    assert claude_plugin["skills"] == "./skills/"
    assert claude_plugin.get("commands") is None
    assert claude_plugin["hooks"] == "./hooks.json"
    assert claude_plugin["mcpServers"] == "./.mcp.json"

    claude_mcp = json.loads(
        (project_root / ".claude" / ".mcp.json").read_text(encoding="utf-8")
    )
    assert "tilth" in claude_mcp["mcpServers"]
    assert "context7" in claude_mcp["mcpServers"]
    assert "tavily" in claude_mcp["mcpServers"]
    assert "serper" not in claude_mcp["mcpServers"]


def test_compiles_a_single_harness_bundle_and_returns_metadata(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    compiled = asyncio.run(
        compile_harness_bundle(project_root=project_root, harness="claude-code")
    )
    assert compiled.harness == "claude-code"
    assert compiled.outputRoot == str(project_root / ".claude")
    assert compiled.pluginMetadata["name"] == "cheese-flow"
    plugin_text = (
        project_root / ".claude" / ".claude-plugin" / "plugin.json"
    ).read_text(encoding="utf-8")
    assert '"name": "cheese-flow"' in plugin_text


def test_emits_agent_frontmatter_with_skills_binding_for_claude_code(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    cook_agent = (project_root / ".claude" / "agents" / "cook.md").read_text(
        encoding="utf-8"
    )
    data, _ = parse_frontmatter(cook_agent)
    assert data["name"] == "cook"
    assert data["model"] == "sonnet"
    assert data["skills"] == ["cheez-read", "cheez-search", "cheez-write"]
    assert data["color"] == "blue"
    assert data["permissionMode"] == "acceptEdits"
    assert "Required skills (prompt contract)" not in cook_agent


def test_drops_claude_only_fields_and_appends_skills_prompt_contract_for_codex(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(project_root=project_root, harnesses=["codex"])
    )
    cook_agent = (project_root / ".codex" / "agents" / "cook.md").read_text(
        encoding="utf-8"
    )
    data, _ = parse_frontmatter(cook_agent)
    assert data["name"] == "cook"
    assert data["model"] == "gpt-5-codex"
    assert "skills" not in data
    assert "color" not in data
    assert "permissionMode" not in data
    assert "Required skills (prompt contract)" in cook_agent
    assert "- cheez-read" in cook_agent
    assert "- cheez-search" in cook_agent
    assert "- cheez-write" in cook_agent


def test_applies_models_yaml_pins_and_overrides(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / "models.yaml").write_text(
        dedent(
            """
            pins:
              claude-code:
                sonnet: claude-sonnet-4-6
            overrides:
              basic-agent:
                claude-code: claude-opus-4-7
            """
        ).lstrip(),
        encoding="utf-8",
    )
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    cook_data, _ = parse_frontmatter(
        (project_root / ".claude" / "agents" / "cook.md").read_text(encoding="utf-8")
    )
    assert cook_data["model"] == "claude-sonnet-4-6"
    basic_data, _ = parse_frontmatter(
        (project_root / ".claude" / "agents" / "basic-agent.md").read_text(
            encoding="utf-8"
        )
    )
    assert basic_data["model"] == "claude-opus-4-7"


def test_validates_the_shipped_skill_metadata() -> None:
    skill = asyncio.run(read_skill(REPO_ROOT, "basic-skill"))
    assert skill.name == "basic-skill"
    assert "portable" in skill.description


def test_renders_a_preview_from_the_template_source() -> None:
    output = asyncio.run(preview_agent(REPO_ROOT, "basic-agent.md.eta", "claude-code"))
    assert "Harness target: Claude Code" in output


def test_rejects_skills_whose_folder_name_does_not_match_the_spec_name(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    (project_root / "agents").mkdir(parents=True)
    (project_root / "skills" / "wrong-name").mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "agents" / "basic-agent.md.eta",
        project_root / "agents" / "basic-agent.md.eta",
    )
    (project_root / "skills" / "wrong-name" / "SKILL.md").write_text(
        "---\nname: basic-skill\ndescription: Portable test skill\n---\n# Wrong\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must match frontmatter name"):
        asyncio.run(
            compile_harness_bundles(
                project_root=project_root, harnesses=["claude-code"]
            )
        )


def test_ignores_non_template_agent_files_and_non_directory_skill_entries(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / "skills" / "nested-dir").mkdir()
    (project_root / "agents" / "README.txt").write_text("ignore me\n", encoding="utf-8")
    (project_root / "skills" / "notes.txt").write_text("ignore me\n", encoding="utf-8")
    (project_root / "skills" / "nested-dir" / "SKILL.md").write_text(
        "---\nname: nested-dir\ndescription: Another portable skill\n---\n# Nested\n",
        encoding="utf-8",
    )

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    manifest = json.loads(
        (project_root / ".claude" / "manifest.json").read_text(encoding="utf-8")
    )
    assert "basic-agent.md" in manifest["agents"]
    assert "cook.md" in manifest["agents"]
    assert "basic-skill" in manifest["skills"]
    assert "nested-dir" in manifest["skills"]
    assert manifest["commands"] == []


def test_emits_dual_surface_artifacts_and_manifests_for_cursor(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(project_root=project_root, harnesses=["cursor"])
    )
    cursor_root = project_root / ".cursor"
    rule = (cursor_root / "rules" / "basic-skill.mdc").read_text(encoding="utf-8")
    command = (cursor_root / "commands" / "basic-skill.md").read_text(
        encoding="utf-8"
    )
    assert "alwaysApply: false" in rule
    assert "description:" in rule
    assert command  # non-empty
    plugin_json = json.loads(
        (cursor_root / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert plugin_json["name"] == "cheese-flow"
    assert plugin_json["rules"] == "./rules/"
    assert plugin_json["skills"] == "./skills/"
    assert plugin_json["agents"] == "./agents/"
    assert plugin_json["commands"] == "./commands/"
    assert plugin_json.get("hooks") is None
    assert plugin_json["mcpServers"] == "./mcp.json"
    mcp_json = json.loads(
        (cursor_root / "mcp.json").read_text(encoding="utf-8")
    )
    assert "tilth" in mcp_json["mcpServers"]
    assert "context7" in mcp_json["mcpServers"]
    assert "tavily" in mcp_json["mcpServers"]


def test_emits_plugin_manifest_mcp_config_and_hooks_for_copilot_cli(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / "hooks.json").write_text(
        json.dumps(
            {"sessionStart": [{"type": "command", "command": "echo start"}]}
        ),
        encoding="utf-8",
    )

    asyncio.run(
        compile_harness_bundles(project_root=project_root, harnesses=["copilot-cli"])
    )
    copilot_root = project_root / ".copilot"
    plugin_json = json.loads(
        (copilot_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert plugin_json["name"] == "cheese-flow"
    assert plugin_json["category"] == "development"
    assert plugin_json["agents"] == "./agents/"
    assert plugin_json["skills"] == "./skills/"
    assert plugin_json["hooks"] == "./hooks.json"
    assert plugin_json["mcpServers"] == "./.mcp.json"
    assert plugin_json.get("commands") is None
    mcp_json = json.loads(
        (copilot_root / ".mcp.json").read_text(encoding="utf-8")
    )
    assert "tilth" in mcp_json["mcpServers"]
    assert "context7" in mcp_json["mcpServers"]
    hooks_json = json.loads(
        (copilot_root / "hooks.json").read_text(encoding="utf-8")
    )
    assert hooks_json["version"] == 1
    assert "sessionStart" in hooks_json["hooks"]


def test_emits_hooks_from_hooks_json_source_into_each_non_cursor_harness(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / "hooks.json").write_text(
        json.dumps(
            {
                "preToolUse": [{"type": "command", "command": "echo pre"}],
                "postToolUse": [{"type": "command", "command": "echo post"}],
            }
        ),
        encoding="utf-8",
    )

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code", "codex"]
        )
    )
    claude_hooks = json.loads(
        (project_root / ".claude" / "hooks.json").read_text(encoding="utf-8")
    )
    assert "preToolUse" in claude_hooks["hooks"]
    assert "postToolUse" in claude_hooks["hooks"]

    codex_hooks = json.loads(
        (project_root / ".codex" / "hooks.json").read_text(encoding="utf-8")
    )
    assert "PreToolUse" in codex_hooks["hooks"]
    assert "PostToolUse" in codex_hooks["hooks"]


def test_reads_plugin_metadata_from_dot_claude_plugin_when_present(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / ".claude-plugin").mkdir()
    custom_meta = {
        "name": "my-custom-plugin",
        "version": "2.0.0",
        "description": "Custom plugin description.",
        "author": {"name": "Test Author"},
        "license": "Apache-2.0",
        "repository": "https://github.com/test/repo",
        "homepage": "https://example.com",
        "keywords": ["test", "plugin"],
    }
    (project_root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(custom_meta), encoding="utf-8"
    )

    asyncio.run(
        compile_harness_bundles(project_root=project_root, harnesses=["claude-code"])
    )
    plugin_json = json.loads(
        (project_root / ".claude" / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert plugin_json["name"] == "my-custom-plugin"
    assert plugin_json["homepage"] == "https://example.com"
    assert plugin_json["keywords"] == ["test", "plugin"]


def test_rethrows_non_enoent_errors_when_reading_plugin_metadata(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    plugin_dir = project_root / ".claude-plugin" / "plugin.json"
    plugin_dir.mkdir(parents=True)
    with pytest.raises((OSError, ValueError)):
        asyncio.run(
            compile_harness_bundles(
                project_root=project_root, harnesses=["claude-code"]
            )
        )


def test_rethrows_non_enoent_errors_when_reading_hooks_json(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    (project_root / "hooks.json").mkdir()
    with pytest.raises((OSError, ValueError)):
        asyncio.run(
            compile_harness_bundles(
                project_root=project_root, harnesses=["claude-code"]
            )
        )


def test_preserves_user_managed_files_at_harness_output_root_across_rebuilds(
    tmp_path: Path,
) -> None:
    project_root = _stage_project(tmp_path)
    claude_root = project_root / ".claude"
    claude_root.mkdir()
    (claude_root / "settings.local.json").write_text(
        '{"theme":"dark"}\n', encoding="utf-8"
    )
    (claude_root / "CLAUDE.md").write_text("# user notes\n", encoding="utf-8")

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )

    assert (
        (claude_root / "settings.local.json").read_text(encoding="utf-8")
        == '{"theme":"dark"}\n'
    )
    assert (
        (claude_root / "CLAUDE.md").read_text(encoding="utf-8") == "# user notes\n"
    )


def test_removes_stale_generated_agents_on_rebuild(tmp_path: Path) -> None:
    project_root = _stage_project(tmp_path)
    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    stale_agent_path = project_root / ".claude" / "agents" / "renamed-away.md"
    stale_agent_path.write_text("stale\n", encoding="utf-8")

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root, harnesses=["claude-code"]
        )
    )
    assert not stale_agent_path.exists()


def test_parses_frontmatter_and_falls_back_to_default_model_when_needed() -> None:
    parsed_data, parsed_body = parse_frontmatter(
        "---\nname: example\ndescription: Parser test\n---\n# Body\n"
    )
    assert parsed_data["name"] == "example"
    assert parsed_body.strip() == "# Body"

    models = HarnessModel.model_validate({"default": "gpt-5.1-codex"})
    assert resolve_model(models, "claude-code") == "gpt-5.1-codex"


def test_validates_allowed_tool_field_variants_for_skills_and_default_tools_for_agents() -> None:
    skill = parse_skill_frontmatter(
        {
            "name": "basic-skill",
            "description": "Portable skill",
            "allowed-tools": "read write",
        }
    )
    agent = parse_agent_frontmatter(
        {
            "name": "basic-agent",
            "description": "Portable agent",
            "models": {"default": "gpt-5.1-codex"},
        }
    )
    assert skill.model_dump(by_alias=True)["allowed-tools"] == "read write"
    assert agent.tools == []
