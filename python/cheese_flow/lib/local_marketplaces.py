"""Port of `src/lib/local-marketplaces.ts` — local marketplace JSON writers.

Mirrors the TS surface: ``write_claude_marketplace`` and
``write_codex_marketplace`` emit harness-specific ``marketplace.json`` files
under the compiled bundle root. Both return a small dataclass describing the
marketplace and plugin names so installer guidance can reference them.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cheese_flow.lib.harness import PluginMetadata


@dataclass(frozen=True)
class MarketplaceInstallDetails:
    marketplaceName: str
    pluginName: str


def _marketplace_name(plugin_name: str) -> str:
    return f"{plugin_name}-local"


async def _write_json_file(file_path: Path, payload: dict[str, Any]) -> None:
    def _write() -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    await asyncio.to_thread(_write)


def _author_payload(metadata: PluginMetadata) -> dict[str, Any]:
    author = metadata["author"]
    payload: dict[str, Any] = {"name": author["name"]}
    if "email" in author:
        payload["email"] = author["email"]
    return payload


def _claude_plugin_entry(metadata: PluginMetadata) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": metadata["name"],
        "source": "./",
        "description": metadata["description"],
        "version": metadata["version"],
        "author": metadata["author"],
        "repository": metadata["repository"],
    }
    if "homepage" in metadata:
        entry["homepage"] = metadata["homepage"]
    if "keywords" in metadata:
        entry["keywords"] = metadata["keywords"]
    entry["strict"] = True
    return entry


async def write_claude_marketplace(
    bundle_root: str,
    metadata: PluginMetadata,
) -> MarketplaceInstallDetails:
    details = MarketplaceInstallDetails(
        marketplaceName=_marketplace_name(metadata["name"]),
        pluginName=metadata["name"],
    )
    payload: dict[str, Any] = {
        "name": details.marketplaceName,
        "owner": _author_payload(metadata),
        "plugins": [_claude_plugin_entry(metadata)],
    }
    await _write_json_file(
        Path(bundle_root) / ".claude-plugin" / "marketplace.json",
        payload,
    )
    return details


async def write_codex_marketplace(
    bundle_root: str,
    metadata: PluginMetadata,
) -> MarketplaceInstallDetails:
    details = MarketplaceInstallDetails(
        marketplaceName=_marketplace_name(metadata["name"]),
        pluginName=metadata["name"],
    )
    payload: dict[str, Any] = {
        "name": details.marketplaceName,
        "interface": {
            "displayName": f"{metadata['name']} Local",
        },
        "plugins": [
            {
                "name": metadata["name"],
                "source": {
                    "source": "local",
                    "path": "./",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Development",
            }
        ],
    }
    await _write_json_file(
        Path(bundle_root) / ".agents" / "plugins" / "marketplace.json",
        payload,
    )
    return details


__all__ = [
    "MarketplaceInstallDetails",
    "write_claude_marketplace",
    "write_codex_marketplace",
]
