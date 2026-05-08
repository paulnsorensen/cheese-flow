"""Port of `src/adapters/codex.ts`."""

from __future__ import annotations

from typing import Any

from cheese_flow.adapters._shared import (
    build_base_manifest,
    build_portable_agent_artifact,
    pascal_matcher_hooks,
)
from cheese_flow.lib.harness import (
    HarnessAdapter,
    HarnessCapabilities,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
)

CODEX_MANIFEST_KEYS: tuple[str, ...] = ("skills", "mcpServers", "apps")


def _build_manifest(
    metadata: PluginMetadata,
    component_paths: ManifestComponentPaths,
) -> dict[str, Any]:
    return build_base_manifest(metadata, component_paths, CODEX_MANIFEST_KEYS)


def _build_hook_config(portable: PortableHooks) -> dict[str, Any]:
    return {"hooks": pascal_matcher_hooks(portable)}


codex_adapter = HarnessAdapter(
    name="codex",
    displayName="Codex",
    outputRoot=".codex",
    agentDirectory="agents",
    skillDirectory="skills",
    commandDirectory="commands",
    defaultModel="gpt-5-codex",
    notes=(
        "Bias instructions toward patch-oriented execution and explicit constraints.",
        "Prefer Codex model identifiers in agent metadata and output.",
    ),
    manifestDir=".codex-plugin",
    buildManifest=_build_manifest,
    mcpFileName=".mcp.json",
    buildHookConfig=_build_hook_config,
    buildAgentArtifact=build_portable_agent_artifact,
    capabilities=HarnessCapabilities(
        skillFrontmatterKeys=frozenset(),
        agentFrontmatterKeys=frozenset(),
        hookEvents=frozenset({"sessionStart", "preToolUse", "postToolUse"}),
        toolNames=frozenset(),
        bootstrapHook=True,
    ),
)
