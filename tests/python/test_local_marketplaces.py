"""Tests for `python/cheese_flow/lib/local_marketplaces.py`.

There is no dedicated `tests/local-marketplaces.test.ts` upstream — the TS
surface is exercised transitively by ``tests/installer.test.ts`` (already
ported in US-008). These tests mirror the TS contract directly against the
Python helpers so any future drift in JSON shape, file location, or
optional-field handling is caught at the unit boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from cheese_flow.lib.harness import PluginMetadata
from cheese_flow.lib.local_marketplaces import (
    MarketplaceInstallDetails,
    write_claude_marketplace,
    write_codex_marketplace,
)


def _full_metadata() -> PluginMetadata:
    return {
        "name": "cheese-flow",
        "version": "1.2.3",
        "description": "Cheese flow plugin",
        "author": {"name": "Paul", "email": "paul@example.com"},
        "license": "MIT",
        "repository": "https://example.com/repo",
        "homepage": "https://example.com",
        "keywords": ["cheese", "flow"],
    }


def _minimal_metadata() -> PluginMetadata:
    return {
        "name": "cheese-flow",
        "version": "1.2.3",
        "description": "Cheese flow plugin",
        "author": {"name": "Paul"},
        "license": "MIT",
        "repository": "https://example.com/repo",
    }


def test_write_claude_marketplace_writes_marketplace_json(tmp_path: Path) -> None:
    details = asyncio.run(write_claude_marketplace(str(tmp_path), _full_metadata()))

    assert isinstance(details, MarketplaceInstallDetails)
    assert details.marketplaceName == "cheese-flow-local"
    assert details.pluginName == "cheese-flow"

    target = tmp_path / ".claude-plugin" / "marketplace.json"
    assert target.exists()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "name": "cheese-flow-local",
        "owner": {"name": "Paul", "email": "paul@example.com"},
        "plugins": [
            {
                "name": "cheese-flow",
                "source": "./",
                "description": "Cheese flow plugin",
                "version": "1.2.3",
                "author": {"name": "Paul", "email": "paul@example.com"},
                "repository": "https://example.com/repo",
                "homepage": "https://example.com",
                "keywords": ["cheese", "flow"],
                "strict": True,
            }
        ],
    }


def test_write_claude_marketplace_omits_optional_fields(tmp_path: Path) -> None:
    asyncio.run(write_claude_marketplace(str(tmp_path), _minimal_metadata()))

    payload = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"),
    )
    plugin = payload["plugins"][0]

    assert "homepage" not in plugin
    assert "keywords" not in plugin
    assert plugin["author"] == {"name": "Paul"}
    assert payload["owner"] == {"name": "Paul"}
    assert plugin["strict"] is True


def test_write_claude_marketplace_creates_parent_directories(tmp_path: Path) -> None:
    bundle_root = tmp_path / "deep" / "nested" / "bundle"

    asyncio.run(write_claude_marketplace(str(bundle_root), _minimal_metadata()))

    assert (bundle_root / ".claude-plugin" / "marketplace.json").exists()


def test_write_claude_marketplace_emits_trailing_newline(tmp_path: Path) -> None:
    asyncio.run(write_claude_marketplace(str(tmp_path), _minimal_metadata()))

    raw = (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")


def test_write_codex_marketplace_writes_marketplace_json(tmp_path: Path) -> None:
    details = asyncio.run(write_codex_marketplace(str(tmp_path), _full_metadata()))

    assert details.marketplaceName == "cheese-flow-local"
    assert details.pluginName == "cheese-flow"

    target = tmp_path / ".agents" / "plugins" / "marketplace.json"
    assert target.exists()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "name": "cheese-flow-local",
        "interface": {"displayName": "cheese-flow Local"},
        "plugins": [
            {
                "name": "cheese-flow",
                "source": {"source": "local", "path": "./"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Development",
            }
        ],
    }


def test_write_codex_marketplace_ignores_metadata_extras(tmp_path: Path) -> None:
    """Codex schema does not surface author/homepage/keywords; ensure parity."""

    asyncio.run(write_codex_marketplace(str(tmp_path), _full_metadata()))

    payload = json.loads(
        (tmp_path / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8",
        ),
    )
    plugin = payload["plugins"][0]

    assert set(plugin.keys()) == {"name", "source", "policy", "category"}


def test_write_codex_marketplace_emits_trailing_newline(tmp_path: Path) -> None:
    asyncio.run(write_codex_marketplace(str(tmp_path), _minimal_metadata()))

    raw = (tmp_path / ".agents" / "plugins" / "marketplace.json").read_text(
        encoding="utf-8",
    )
    assert raw.endswith("\n")


@pytest.mark.parametrize("plugin_name", ["foo", "bar-baz", "cheese-flow"])
def test_marketplace_name_is_plugin_name_with_local_suffix(
    tmp_path: Path, plugin_name: str,
) -> None:
    metadata: PluginMetadata = {
        "name": plugin_name,
        "version": "0.0.1",
        "description": "x",
        "author": {"name": "Paul"},
        "license": "MIT",
        "repository": "https://example.com/repo",
    }

    claude = asyncio.run(write_claude_marketplace(str(tmp_path / plugin_name), metadata))
    codex = asyncio.run(write_codex_marketplace(str(tmp_path / plugin_name), metadata))

    assert claude.marketplaceName == f"{plugin_name}-local"
    assert codex.marketplaceName == f"{plugin_name}-local"
