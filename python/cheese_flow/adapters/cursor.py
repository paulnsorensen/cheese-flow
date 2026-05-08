"""Port of `src/adapters/cursor.ts`.

The TS adapter ships an `emitSurface` callback that reads each skill's
SKILL.md and renders both a Cursor `.mdc` rule and a `.md` slash command.
That code path imports `parseFrontmatter` from `lib/frontmatter.ts`, which
the migration spec assigns to US-004. The callable is therefore wired in
US-004 alongside the frontmatter port; the rest of the cursor adapter
(declarative metadata, manifest builder, hook config) lands here in US-003
so the registry shape is complete.
"""

from __future__ import annotations

from typing import Any

from cheese_flow.adapters._shared import (
    build_base_manifest,
    build_portable_agent_artifact,
)
from cheese_flow.lib.harness import (
    HarnessAdapter,
    HarnessCapabilities,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
)

CURSOR_MANIFEST_KEYS: tuple[str, ...] = (
    "rules",
    "skills",
    "agents",
    "commands",
    "hooks",
    "mcpServers",
)


def _build_manifest(
    metadata: PluginMetadata,
    component_paths: ManifestComponentPaths,
) -> dict[str, Any]:
    return build_base_manifest(metadata, component_paths, CURSOR_MANIFEST_KEYS)


def _build_hook_config(_portable: PortableHooks) -> None:
    return None


cursor_adapter = HarnessAdapter(
    name="cursor",
    displayName="Cursor",
    outputRoot=".cursor",
    agentDirectory="agents",
    skillDirectory="skills",
    defaultModel="auto",
    notes=(
        "Cursor exposes skills on two surfaces: ambient rules (.cursor/rules/*.mdc) and slash commands (.cursor/commands/*.md). Both are emitted from the same SKILL.md source.",  # noqa: E501
        "MCP-only tool surface applies; Cursor does not support hooks — hook emission is skipped with an info log.",  # noqa: E501
    ),
    manifestDir=".cursor-plugin",
    buildManifest=_build_manifest,
    mcpFileName="mcp.json",
    buildHookConfig=_build_hook_config,
    buildAgentArtifact=build_portable_agent_artifact,
    capabilities=HarnessCapabilities(
        skillFrontmatterKeys=frozenset(),
        agentFrontmatterKeys=frozenset(),
        hookEvents=frozenset(),
        toolNames=frozenset(),
        bootstrapHook=False,
    ),
)
