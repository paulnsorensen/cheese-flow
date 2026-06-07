"""Port of `src/adapters/claude-code.ts`."""

from __future__ import annotations

from typing import Any

from cheese_flow.adapters._shared import (
    build_base_agent_artifact,
    build_base_manifest,
    camel_case_hooks,
)
from cheese_flow.lib.harness import (
    AgentArtifact,
    AgentArtifactInput,
    HarnessAdapter,
    HarnessCapabilities,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
)

CLAUDE_AGENT_KEY_ORDER: tuple[str, ...] = (
    "skills",
    "color",
    "effort",
    "disallowedTools",
    "permissionMode",
)
CLAUDE_AGENT_KEYS: frozenset[str] = frozenset(CLAUDE_AGENT_KEY_ORDER)

CLAUDE_MANIFEST_KEYS: tuple[str, ...] = (
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
    return build_base_manifest(metadata, component_paths, CLAUDE_MANIFEST_KEYS)


def _build_hook_config(portable: PortableHooks) -> dict[str, Any]:
    return {"hooks": camel_case_hooks(portable)}


def _build_agent_artifact(artifact_input: AgentArtifactInput) -> AgentArtifact:
    return build_base_agent_artifact(artifact_input, CLAUDE_AGENT_KEY_ORDER)


claude_code_adapter = HarnessAdapter(
    name="claude-code",
    displayName="Claude Code",
    outputRoot=".claude",
    agentDirectory="agents",
    skillDirectory="skills",
    commandDirectory="commands",
    defaultModel="sonnet",
    notes=(
        "Use concise markdown headings and explicit tool guidance.",
        "Prefer Claude model identifiers in agent metadata and output.",
    ),
    manifestDir=".claude-plugin",
    buildManifest=_build_manifest,
    mcpFileName=".mcp.json",
    buildHookConfig=_build_hook_config,
    buildAgentArtifact=_build_agent_artifact,
    capabilities=HarnessCapabilities(
        skillFrontmatterKeys=frozenset({"model", "context"}),
        agentFrontmatterKeys=CLAUDE_AGENT_KEYS,
        hookEvents=frozenset(
            {
                "sessionStart",
                "sessionEnd",
                "preToolUse",
                "postToolUse",
                "stop",
                "subagentStop",
                "notification",
                "preCompact",
                "userPromptSubmit",
            },
        ),
        toolNames=frozenset(
            {
                "Agent",
                "Task",
                "NotebookEdit",
                "WebSearch",
                "WebFetch",
                "TodoWrite",
            },
        ),
        bootstrapHook=True,
    ),
)
