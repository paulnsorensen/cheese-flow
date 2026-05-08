"""Port of `src/lib/emit.ts` — write plugin manifest, MCP config, hooks files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.harness import (
    CANONICAL_MCP_SERVERS,
    PORTABLE_EVENTS,
    HarnessName,
    HooksSource,
    ManifestComponentPaths,
    PluginMetadata,
    PortableEvent,
    PortableHooks,
)

_BOOTSTRAP_COMMAND_MARKER = "hooks/cheese-bootstrap.sh"


def _filter_portable_events(source: HooksSource) -> PortableHooks:
    portable: PortableHooks = {}
    portable_set: frozenset[str] = frozenset(PORTABLE_EVENTS)
    for event, entries in source.items():
        if entries is None:
            continue
        if event in portable_set:
            portable[event] = entries  # type: ignore[index]
        else:
            print(
                f"[cheese-flow] skipping non-portable hook event: {event}",
                file=sys.stderr,
            )
    return portable


def _filter_bootstrap_entries(portable: PortableHooks) -> PortableHooks:
    result: PortableHooks = {}
    for event, entries in portable.items():
        if entries is None:
            continue
        kept = [
            entry
            for entry in entries
            if _BOOTSTRAP_COMMAND_MARKER not in entry["command"]
        ]
        if len(kept) > 0:
            event_key: PortableEvent = event  # type: ignore[assignment]
            result[event_key] = kept
    return result


def _dump_json(payload: object) -> str:
    """Match Node ``JSON.stringify(value, null, 2)`` formatting (with a trailing newline)."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def emit_plugin_manifest(
    harness: HarnessName,
    metadata: PluginMetadata,
    output_root: str | Path,
    component_paths: ManifestComponentPaths | None = None,
) -> Path:
    component_paths = component_paths or {}
    adapter = HARNESS_ADAPTERS[harness]
    manifest = adapter.buildManifest(metadata, component_paths)
    manifest_dir = Path(output_root) / adapter.manifestDir
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "plugin.json"
    manifest_path.write_text(_dump_json(manifest), encoding="utf-8")
    return manifest_path


def emit_mcp_config(harness: HarnessName, output_root: str | Path) -> Path:
    adapter = HARNESS_ADAPTERS[harness]
    Path(output_root).mkdir(parents=True, exist_ok=True)
    config = {"mcpServers": CANONICAL_MCP_SERVERS}
    output_path = Path(output_root) / adapter.mcpFileName
    output_path.write_text(_dump_json(config), encoding="utf-8")
    return output_path


def emit_hooks(
    harness: HarnessName,
    source: HooksSource,
    output_root: str | Path,
) -> Path | None:
    adapter = HARNESS_ADAPTERS[harness]
    portable = _filter_portable_events(source)
    if not adapter.capabilities.bootstrapHook:
        portable = _filter_bootstrap_entries(portable)
    payload = adapter.buildHookConfig(portable)

    if payload is None:
        # Mirror TS ``console.info`` — informational output goes to stdout so
        # ``cheese compile`` log scrapers see the message in the same stream.
        print(f"[cheese-flow] hooks not supported in {harness} target; skipping")
        return None

    Path(output_root).mkdir(parents=True, exist_ok=True)
    output_path = Path(output_root) / "hooks.json"
    output_path.write_text(_dump_json(payload), encoding="utf-8")
    return output_path
