"""Port of `src/adapters/copilot-cli.ts`."""

from __future__ import annotations

from typing import Any

from cheese_flow.adapters._shared import (
    build_base_manifest,
    build_portable_agent_artifact,
    camel_case_hooks,
)
from cheese_flow.lib.harness import (
    HarnessAdapter,
    HarnessCapabilities,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
)

COPILOT_MANIFEST_KEYS: tuple[str, ...] = (
    "agents",
    "skills",
    "commands",
    "hooks",
    "mcpServers",
)


def _build_manifest(
    metadata: PluginMetadata,
    component_paths: ManifestComponentPaths,
) -> dict[str, Any]:
    base = build_base_manifest(metadata, component_paths, COPILOT_MANIFEST_KEYS)
    return {**base, "category": "development", "strict": True}


def _build_hook_config(portable: PortableHooks) -> dict[str, Any]:
    return {"version": 1, "hooks": camel_case_hooks(portable)}


copilot_cli_adapter = HarnessAdapter(
    name="copilot-cli",
    displayName="GitHub Copilot CLI",
    outputRoot=".copilot",
    agentDirectory="agents",
    skillDirectory="skills",
    defaultModel="gpt-5",
    notes=(
        "Copilot CLI resolves plugin manifests from .claude-plugin/plugin.json as its fourth search path, so the same manifest shape serves both Claude Code and Copilot CLI installations.",  # noqa: E501
    ),
    manifestDir=".claude-plugin",
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
