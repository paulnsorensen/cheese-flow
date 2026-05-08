"""Port of `src/domain/harness.ts` — harness domain types.

Per the migration spec's Implementation Notes, the TS domain types live on
the slice as `python/cheese_flow/lib/harness.py`. This module is the typed
seam that adapters and (later) the compile pipeline both consume.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    TypedDict,
)

CHEESE_DIR = ".cheese"

HarnessName = Literal["claude-code", "codex", "cursor", "copilot-cli"]

PortableEvent = Literal["sessionStart", "preToolUse", "postToolUse"]
PORTABLE_EVENTS: tuple[PortableEvent, ...] = (
    "sessionStart",
    "preToolUse",
    "postToolUse",
)


class _HookEntryRequired(TypedDict):
    type: str
    command: str


class HookEntry(_HookEntryRequired, total=False):
    """Mirror of `HookEntry` (`type`, `command` required; `timeout` optional)."""

    timeout: int


HooksSource = dict[str, list[HookEntry]]
PortableHooks = dict[PortableEvent, list[HookEntry]]


class _PluginAuthorRequired(TypedDict):
    name: str


class PluginAuthor(_PluginAuthorRequired, total=False):
    email: str
    url: str


class _PluginMetadataRequired(TypedDict):
    name: str
    version: str
    description: str
    author: PluginAuthor
    license: str
    repository: str


class PluginMetadata(_PluginMetadataRequired, total=False):
    """Mirror of `PluginMetadata` from `pluginMetadataSchema`."""

    homepage: str
    keywords: list[str]


class _McpServerConfigRequired(TypedDict):
    command: str
    args: list[str]


class McpServerConfig(_McpServerConfigRequired, total=False):
    env: dict[str, str]


CANONICAL_MCP_SERVERS: dict[str, McpServerConfig] = {
    "milknado": {
        "command": "npx",
        "args": ["tsx", "src/index.ts", "mcp"],
    },
    "tilth": {"command": "npx", "args": ["tilth", "--mcp", "--edit"]},
    "context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    },
    "tavily": {
        "command": "npx",
        "args": ["-y", "tavily-mcp@latest"],
        "env": {"TAVILY_API_KEY": "${TAVILY_API_KEY}"},
    },
}


class SurfaceEmissionResult(TypedDict):
    rules: list[str]
    commands: list[str]


class ManifestComponentPaths(TypedDict, total=False):
    agents: str
    skills: str
    commands: str
    hooks: str
    mcpServers: str
    rules: str
    apps: str


class _AgentFrontmatterRequired(TypedDict):
    name: str
    description: str
    tools: list[str]
    skills: list[str]
    disallowedTools: list[str]


class AgentFrontmatterFields(_AgentFrontmatterRequired, total=False):
    """Narrow record passed to `build_base_agent_artifact`.

    Required keys: `name`, `description`, `tools`, `skills`, `disallowedTools`.
    Optional keys: `color`, `effort`, `permissionMode`.
    """

    color: str
    effort: str
    permissionMode: str


@dataclass(frozen=True)
class AgentArtifactInput:
    frontmatter: AgentFrontmatterFields
    resolvedModel: str


@dataclass(frozen=True)
class AgentArtifact:
    frontmatter: dict[str, Any]
    appendix: str


@dataclass(frozen=True)
class HarnessCapabilities:
    skillFrontmatterKeys: frozenset[str]
    agentFrontmatterKeys: frozenset[str]
    hookEvents: frozenset[str]
    toolNames: frozenset[str]
    bootstrapHook: bool


BuildManifest = Callable[[PluginMetadata, ManifestComponentPaths], dict[str, Any]]
BuildHookConfig = Callable[[PortableHooks], dict[str, Any] | None]
BuildAgentArtifact = Callable[[AgentArtifactInput], AgentArtifact]
EmitSurface = Callable[[str, str], Awaitable[SurfaceEmissionResult]]


@dataclass(frozen=True)
class HarnessAdapter:
    """Mirror of the TS `HarnessAdapter` interface as a frozen dataclass."""

    name: HarnessName
    displayName: str
    outputRoot: str
    agentDirectory: str
    skillDirectory: str
    defaultModel: str
    notes: tuple[str, ...]
    manifestDir: str
    mcpFileName: str
    buildManifest: BuildManifest
    buildHookConfig: BuildHookConfig
    buildAgentArtifact: BuildAgentArtifact
    capabilities: HarnessCapabilities
    commandDirectory: str | None = None
    emitSurface: EmitSurface | None = None
