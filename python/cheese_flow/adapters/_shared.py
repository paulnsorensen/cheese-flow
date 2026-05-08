"""Port of `src/adapters/_shared.ts` — shared manifest + hook + agent builders."""

from __future__ import annotations

from typing import Any

from cheese_flow.lib.harness import (
    PORTABLE_EVENTS,
    AgentArtifact,
    AgentArtifactInput,
    HookEntry,
    ManifestComponentPaths,
    PluginMetadata,
    PortableHooks,
)

_PASCAL_MAP: dict[str, str] = {
    "sessionStart": "SessionStart",
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
}

_DEFAULT_HOOK_TIMEOUT = 600

_EMPTY_AGENT_KEYS: frozenset[str] = frozenset()


def _pick_manifest_paths(
    component_paths: ManifestComponentPaths,
    supported_keys: tuple[str, ...],
) -> dict[str, str]:
    return {
        key: component_paths[key]  # type: ignore[literal-required]
        for key in supported_keys
        if key in component_paths and component_paths[key] is not None  # type: ignore[literal-required]
    }


def build_base_manifest(
    metadata: PluginMetadata,
    component_paths: ManifestComponentPaths,
    supported_keys: tuple[str, ...],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": metadata["name"],
        "version": metadata["version"],
        "description": metadata["description"],
        "author": metadata["author"],
        "license": metadata["license"],
        "repository": metadata["repository"],
    }
    homepage = metadata.get("homepage")
    if homepage is not None:
        result["homepage"] = homepage
    keywords = metadata.get("keywords")
    if keywords is not None:
        result["keywords"] = keywords
    result.update(_pick_manifest_paths(component_paths, supported_keys))
    return result


def camel_case_hooks(portable: PortableHooks) -> dict[str, list[HookEntry]]:
    result: dict[str, list[HookEntry]] = {}
    for event in PORTABLE_EVENTS:
        entries = portable.get(event)
        if entries is not None:
            result[event] = entries
    return result


def pascal_matcher_hooks(portable: PortableHooks) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for event in PORTABLE_EVENTS:
        entries = portable.get(event)
        if entries is None:
            continue
        result[_PASCAL_MAP[event]] = [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": entry["type"],
                        "command": entry["command"],
                        "timeout": entry.get("timeout", _DEFAULT_HOOK_TIMEOUT),
                    },
                ],
            }
            for entry in entries
        ]
    return result


def _build_skills_appendix(skills: list[str]) -> str:
    lines = "\n".join(f"- {skill}" for skill in skills)
    return (
        "\n## Required skills (prompt contract)\n\n"
        "This harness does not expose a structured skills binding, so treat the\n"
        "following skill names as a hard prompt contract — invoke them by name when\n"
        "the workflow calls for their behavior:\n\n"
        f"{lines}\n"
    )


def build_base_agent_artifact(
    artifact_input: AgentArtifactInput,
    agent_frontmatter_keys: frozenset[str],
) -> AgentArtifact:
    frontmatter = artifact_input.frontmatter
    data: dict[str, Any] = {
        "name": frontmatter["name"],
        "description": frontmatter["description"],
        "model": artifact_input.resolvedModel,
    }
    tools = frontmatter["tools"]
    if len(tools) > 0:
        data["tools"] = tools
    raw: dict[str, Any] = dict(frontmatter)
    for key in agent_frontmatter_keys:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, list) and len(value) == 0:
            continue
        data[key] = value
    skills = frontmatter["skills"]
    appendix = (
        ""
        if "skills" in agent_frontmatter_keys or len(skills) == 0
        else _build_skills_appendix(skills)
    )
    return AgentArtifact(frontmatter=data, appendix=appendix)


def build_portable_agent_artifact(
    artifact_input: AgentArtifactInput,
) -> AgentArtifact:
    return build_base_agent_artifact(artifact_input, _EMPTY_AGENT_KEYS)
