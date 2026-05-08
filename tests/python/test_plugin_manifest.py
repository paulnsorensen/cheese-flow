"""Port of ``tests/plugin-manifest.test.ts`` — covers ``emit_plugin_manifest``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.lib.emit import emit_plugin_manifest

BASE_METADATA = {
    "name": "cheese-flow",
    "version": "0.1.0",
    "description": "Multi-harness plugin compiler",
    "author": {"name": "Cheese Lord"},
    "license": "MIT",
    "repository": "https://github.com/paulnsorensen/cheese-flow",
}


def test_emits_valid_claude_plugin_for_claude_code(tmp_path: Path) -> None:
    emit_plugin_manifest("claude-code", BASE_METADATA, tmp_path)
    manifest = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "cheese-flow"
    assert manifest["version"] == "0.1.0"
    assert manifest["author"] == {"name": "Cheese Lord"}


def test_emits_valid_claude_plugin_for_copilot_cli(tmp_path: Path) -> None:
    emit_plugin_manifest("copilot-cli", BASE_METADATA, tmp_path)
    manifest = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "cheese-flow"


def test_emits_valid_cursor_plugin(tmp_path: Path) -> None:
    emit_plugin_manifest("cursor", BASE_METADATA, tmp_path)
    manifest = json.loads(
        (tmp_path / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "cheese-flow"


def test_emits_valid_codex_plugin(tmp_path: Path) -> None:
    emit_plugin_manifest("codex", BASE_METADATA, tmp_path)
    manifest = json.loads(
        (tmp_path / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "cheese-flow"


def test_includes_homepage_and_keywords_in_codex_manifest(tmp_path: Path) -> None:
    metadata = {
        **BASE_METADATA,
        "homepage": "https://example.invalid/cheese",
        "keywords": ["cheese", "flow"],
    }
    emit_plugin_manifest("codex", metadata, tmp_path)
    manifest = json.loads(
        (tmp_path / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["homepage"] == "https://example.invalid/cheese"
    assert manifest["keywords"] == ["cheese", "flow"]


def test_rejects_metadata_with_missing_required_name_field(tmp_path: Path) -> None:
    invalid_metadata = {
        "version": "0.1.0",
        "description": "Multi-harness plugin compiler",
        "author": {"name": "Cheese Lord"},
        "license": "MIT",
        "repository": "https://github.com/paulnsorensen/cheese-flow",
    }
    with pytest.raises(Exception):  # noqa: B017,PT011 — pydantic ValidationError
        emit_plugin_manifest("claude-code", invalid_metadata, tmp_path)  # type: ignore[arg-type]
