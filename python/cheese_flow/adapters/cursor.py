"""Port of `src/adapters/cursor.ts`.

Includes the `emit_surface` callback wired in US-004 alongside the
frontmatter port. The callback reads each skill's SKILL.md and renders both
a Cursor `.mdc` rule and a `.md` slash command in parallel.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cheese_flow.adapters._shared import (
    build_base_manifest,
    build_portable_agent_artifact,
)
from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.harness import (
    HarnessAdapter,
    HarnessCapabilities,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
    SurfaceEmissionResult,
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


def _build_rule_content(description: str, body: str) -> str:
    return f"---\ndescription: {description}\nglobs:\nalwaysApply: false\n---\n{body.strip()}\n"


async def _emit_skill(
    skill_name: str,
    skill_md_path: Path,
    rules_dir: Path,
    commands_dir: Path,
) -> tuple[str, str] | None:
    if not skill_md_path.exists():
        return None
    content = skill_md_path.read_text(encoding="utf-8")
    data, body = parse_frontmatter(content)
    description = (data or {}).get("description", "") if isinstance(data, dict) else ""

    rule_content = _build_rule_content(description, body)
    command_content = f"{body.strip()}\n"

    rule_path = rules_dir / f"{skill_name}.mdc"
    command_path = commands_dir / f"{skill_name}.md"

    await asyncio.to_thread(rule_path.write_text, rule_content, encoding="utf-8")
    await asyncio.to_thread(command_path.write_text, command_content, encoding="utf-8")

    return (str(rule_path), str(command_path))


async def _emit_cursor_skill_surface(skills_dir: str, output_root: str) -> SurfaceEmissionResult:
    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        return {"rules": [], "commands": []}

    rules_dir = Path(output_root) / "rules"
    commands_dir = Path(output_root) / "commands"
    rules_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)

    rules: list[str] = []
    commands: list[str] = []

    for entry in sorted(skills_path.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        skill_md_path = entry / "SKILL.md"
        result = await _emit_skill(entry.name, skill_md_path, rules_dir, commands_dir)
        if result is not None:
            rules.append(result[0])
            commands.append(result[1])

    return {"rules": rules, "commands": commands}


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
    emitSurface=_emit_cursor_skill_surface,
    capabilities=HarnessCapabilities(
        skillFrontmatterKeys=frozenset(),
        agentFrontmatterKeys=frozenset(),
        hookEvents=frozenset(),
        toolNames=frozenset(),
        bootstrapHook=False,
    ),
)
