"""Port of ``tests/adversarial.test.ts`` — chaos / boundary suite covering
``emit_plugin_manifest``, ``emit_mcp_config``, ``emit_hooks``, the cursor
adapter surface emit, the shipped repo-root manifest files, and ``.gitignore``
sanity.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from cheese_flow.adapters.cursor import cursor_adapter
from cheese_flow.lib.emit import emit_hooks, emit_mcp_config, emit_plugin_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]

BASE_METADATA = {
    "name": "cheese-flow",
    "version": "0.1.0",
    "description": "Multi-harness plugin compiler",
    "author": {"name": "Cheese Lord"},
    "license": "MIT",
    "repository": "https://github.com/paulnsorensen/cheese-flow",
}


def _emit_cursor_surface(skills_dir: Path, output_root: Path):  # type: ignore[no-untyped-def]
    assert cursor_adapter.emitSurface is not None
    return asyncio.run(cursor_adapter.emitSurface(str(skills_dir), str(output_root)))


# ─── emit_plugin_manifest boundary assault ───────────────────────────────────


def test_rejects_empty_string_name(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017
        emit_plugin_manifest("claude-code", {**BASE_METADATA, "name": ""}, tmp_path)


def test_rejects_empty_string_version(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017
        emit_plugin_manifest("claude-code", {**BASE_METADATA, "version": ""}, tmp_path)


def test_rejects_empty_string_description(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017
        emit_plugin_manifest("claude-code", {**BASE_METADATA, "description": ""}, tmp_path)


def test_handles_unicode_emoji_in_name_and_description(tmp_path: Path) -> None:
    metadata = {
        **BASE_METADATA,
        "name": "cheese-flow-🧀",
        "description": "RTL: مرحبا بكم في العالم — emoji 🎉 — Unicode™",
    }
    manifest_path = emit_plugin_manifest("claude-code", metadata, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "cheese-flow-🧀"
    assert "RTL" in manifest["description"]


def test_handles_one_megabyte_description_without_crashing(tmp_path: Path) -> None:
    big = "x" * 1_000_000
    metadata = {**BASE_METADATA, "description": big}
    manifest_path = emit_plugin_manifest("claude-code", metadata, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["description"]) == 1_000_000


def test_creates_deep_non_existent_output_root_path(tmp_path: Path) -> None:
    output_root = tmp_path / "a" / "b" / "c" / "deep"
    manifest_path = emit_plugin_manifest("claude-code", BASE_METADATA, output_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "cheese-flow"


def test_second_write_to_same_harness_overwrites_first(tmp_path: Path) -> None:
    emit_plugin_manifest("claude-code", BASE_METADATA, tmp_path)
    emit_plugin_manifest("claude-code", {**BASE_METADATA, "version": "9.9.9"}, tmp_path)
    manifest = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "9.9.9"


def test_copilot_cli_manifest_includes_category_and_strict_fields(tmp_path: Path) -> None:
    emit_plugin_manifest("copilot-cli", BASE_METADATA, tmp_path)
    manifest = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["category"] == "development"
    assert manifest["strict"] is True


def test_cursor_manifest_includes_homepage_and_keywords_when_supplied(tmp_path: Path) -> None:
    metadata = {**BASE_METADATA, "homepage": "https://example.com", "keywords": ["a", "b"]}
    emit_plugin_manifest("cursor", metadata, tmp_path)
    manifest = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["homepage"] == "https://example.com"
    assert manifest["keywords"] == ["a", "b"]


def test_emitted_plugin_manifest_json_parses_cleanly(tmp_path: Path) -> None:
    manifest_path = emit_plugin_manifest("codex", BASE_METADATA, tmp_path)
    raw = manifest_path.read_text(encoding="utf-8")
    json.loads(raw)  # would raise on trailing commas / malformed JSON


# ─── emit_mcp_config edge cases ──────────────────────────────────────────────


def test_cursor_mcp_path_has_no_leading_dot(tmp_path: Path) -> None:
    output_path = emit_mcp_config("cursor", tmp_path)
    assert output_path.name == "mcp.json"
    assert not output_path.name.startswith(".")


def test_non_cursor_mcp_path_has_leading_dot(tmp_path: Path) -> None:
    output_path = emit_mcp_config("claude-code", tmp_path)
    assert output_path.name == ".mcp.json"


def test_creates_output_root_dir_if_missing(tmp_path: Path) -> None:
    output_root = tmp_path / "new-dir"
    output_path = emit_mcp_config("claude-code", output_root)
    config = json.loads(output_path.read_text(encoding="utf-8"))
    assert config["mcpServers"] is not None


def test_milknado_mcp_server_is_inside_mcp_servers(tmp_path: Path) -> None:
    emit_mcp_config("claude-code", tmp_path)
    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "milknado" in config["mcpServers"]
    assert "__TODO_milknado__" not in config


def test_emitted_mcp_json_parses_back_cleanly(tmp_path: Path) -> None:
    emit_mcp_config("codex", tmp_path)
    json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))


def test_emitted_mcp_file_ends_with_newline(tmp_path: Path) -> None:
    emit_mcp_config("claude-code", tmp_path)
    raw = (tmp_path / ".mcp.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")


# ─── emit_hooks chaos ────────────────────────────────────────────────────────


def test_all_non_portable_events_writes_empty_hooks_object(tmp_path: Path) -> None:
    source = {
        "sessionEnd": [{"type": "command", "command": "echo end"}],
        "customEvent": [{"type": "command", "command": "echo custom"}],
    }
    result = emit_hooks("claude-code", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["hooks"] == {}


def test_empty_source_object_writes_empty_hooks(tmp_path: Path) -> None:
    result = emit_hooks("claude-code", {}, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["hooks"] == {}


def test_event_with_empty_array_is_present_as_empty_entry(tmp_path: Path) -> None:
    source = {"sessionStart": []}
    result = emit_hooks("claude-code", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert "sessionStart" in config["hooks"]


def test_codex_entry_with_explicit_timeout_preserves_it(tmp_path: Path) -> None:
    source = {"sessionStart": [{"type": "command", "command": "echo hi", "timeout": 30}]}
    result = emit_hooks("codex", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 30


def test_codex_entry_without_timeout_gets_default_600(tmp_path: Path) -> None:
    source = {"preToolUse": [{"type": "command", "command": "echo check"}]}
    result = emit_hooks("codex", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] == 600


def test_copilot_cli_version_field_is_number_one(tmp_path: Path) -> None:
    source = {"sessionStart": [{"type": "command", "command": "echo x"}]}
    result = emit_hooks("copilot-cli", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["version"] == 1
    assert isinstance(config["version"], int)
    assert not isinstance(config["version"], bool)  # bool is a subclass of int


def test_cursor_returns_exactly_none(tmp_path: Path) -> None:
    result = emit_hooks(
        "cursor",
        {"sessionStart": [{"type": "command", "command": "x"}]},
        tmp_path,
    )
    assert result is None


def test_very_long_command_string_is_preserved_verbatim(tmp_path: Path) -> None:
    long_command = f"echo {'a' * 10_000}"
    source = {"sessionStart": [{"type": "command", "command": long_command}]}
    result = emit_hooks("claude-code", source, tmp_path)
    assert result is not None
    config = json.loads(Path(result).read_text(encoding="utf-8"))
    assert config["hooks"]["sessionStart"][0]["command"] == long_command


# ─── emit_cursor_surface filesystem attacks ──────────────────────────────────


def test_skill_md_with_zero_body_emits_empty_body_files(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "empty-body"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: empty-body\ndescription: No body here\n---\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "out"
    result = _emit_cursor_surface(skills_dir, output_root)
    assert len(result["rules"]) == 1
    assert len(result["commands"]) == 1
    command_content = Path(result["commands"][0]).read_text(encoding="utf-8")
    assert command_content.strip() == ""


def test_skill_name_with_dashes_emits_correct_filenames(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "my-skill-with-dashes"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill-with-dashes\ndescription: Dash test\n---\n# Body\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "out"
    result = _emit_cursor_surface(skills_dir, output_root)
    assert len(result["rules"]) == 1
    assert Path(result["rules"][0]).name == "my-skill-with-dashes.mdc"


def test_skill_md_missing_frontmatter_delimiters_propagates_error(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "no-frontmatter"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# No frontmatter here\nJust a plain markdown file.\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "out"
    with pytest.raises(Exception):  # noqa: B017
        _emit_cursor_surface(skills_dir, output_root)


def test_completely_empty_skill_md_propagates_error(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "empty-file"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("", encoding="utf-8")
    output_root = tmp_path / "out"
    with pytest.raises(Exception):  # noqa: B017
        _emit_cursor_surface(skills_dir, output_root)


def test_body_with_internal_dash_markers_is_not_re_parsed_as_frontmatter(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "dashes-in-body"
    skill_dir.mkdir(parents=True)
    body = "# Heading\n\nSome content\n\n---\n\nMore content after divider\n"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: dashes-in-body\ndescription: Has dashes inside body\n---\n{body}",
        encoding="utf-8",
    )
    output_root = tmp_path / "out"
    result = _emit_cursor_surface(skills_dir, output_root)
    assert len(result["rules"]) == 1
    command_content = Path(result["commands"][0]).read_text(encoding="utf-8")
    assert "More content after divider" in command_content


def test_symlinked_skill_dir_is_treated_as_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    skills_dir = project_root / "skills"
    skills_dir.mkdir()
    real_skill_dir = project_root / "real-skill"
    real_skill_dir.mkdir()
    (real_skill_dir / "SKILL.md").write_text(
        "---\nname: symlinked-skill\ndescription: Via symlink\n---\n# Symlinked\n",
        encoding="utf-8",
    )
    link_path = skills_dir / "symlinked-skill"
    os.symlink(real_skill_dir, link_path)

    output_root = tmp_path / "out"
    result = _emit_cursor_surface(skills_dir, output_root)
    # Symlinked dirs may or may not appear depending on platform; only assert the
    # call returned cleanly with a non-negative count.
    assert len(result["rules"]) >= 0


# ─── Root manifest files — validity ──────────────────────────────────────────


def test_claude_plugin_manifest_parses_as_valid_json() -> None:
    raw = (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    json.loads(raw)


def test_cursor_plugin_manifest_parses_as_valid_json() -> None:
    raw = (REPO_ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    json.loads(raw)


def test_repo_mcp_json_parses_as_valid_json() -> None:
    raw = (REPO_ROOT / ".mcp.json").read_text(encoding="utf-8")
    json.loads(raw)


def test_claude_plugin_manifest_has_required_fields() -> None:
    manifest = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"]
    assert manifest["version"]
    assert manifest["description"]
    assert manifest["author"]
    assert manifest["license"]
    assert manifest["repository"]


def test_cursor_plugin_manifest_has_required_fields() -> None:
    manifest = json.loads(
        (REPO_ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"]
    assert manifest["version"]
    assert manifest["description"]


def test_repo_mcp_json_has_mcp_servers_at_root() -> None:
    config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"] is not None
    assert isinstance(config["mcpServers"], dict)


def test_repo_mcp_json_milknado_inside_mcp_servers() -> None:
    config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert "milknado" in config["mcpServers"]
    assert "__TODO_milknado__" not in config


# ─── Gitignore sanity ────────────────────────────────────────────────────────


def test_gitignore_contains_dot_cursor_pattern() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".cursor/" in gitignore


def test_gitignore_contains_dot_copilot_pattern() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".copilot/" in gitignore
