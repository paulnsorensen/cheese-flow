from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.runtime import write_workspace_file
from cheese_flow.profiles.launch_policy import ValidatedLaunchPolicy
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.rendering.permissions import launch_permission_rules
from cheese_flow.profiles.rendering.template import mcp_entry_for_harness

_SECTIONS_WITH_SOURCE_DIR = (
    "mcps",
    "agents",
    "skills",
    "commands",
    "hooks",
    "native_plugins",
)


def build_claude_isolation(
    profile: ResolvedProfile,
    policy: ValidatedLaunchPolicy,
    workspace: Path,
    *,
    environment: Mapping[str, str],
) -> LaunchSpec:
    """Build the closed-world Claude launch and its ephemeral inputs."""
    try:
        if policy.harness != "claude" or not policy.isolated:
            raise ValueError("Claude isolation requires an isolated Claude policy")
        if not isinstance(workspace, Path) or not workspace.is_dir():
            raise ValueError("Claude isolation workspace does not exist")

        child_environment = {**environment, **profile.env}
        mcp_path = _write_mcp_config(profile, workspace, child_environment)
        settings_path = _write_settings(profile, workspace)
        plugin_dir = _write_skills_plugin(profile, workspace)

        arguments = [
            "--bare",
            "--strict-mcp-config",
            "--mcp-config",
            str(mcp_path),
            "--setting-sources",
            "",
        ]
        if profile.tools:
            arguments.extend(("--tools", ",".join(profile.tools)))
        if profile.system_prompt:
            arguments.extend(("--append-system-prompt-file", str(_system_prompt_path(profile))))
        if settings_path is not None:
            arguments.extend(("--settings", str(settings_path)))
        if plugin_dir is not None:
            arguments.extend(("--plugin-dir", str(plugin_dir)))

        arguments.extend(policy.profile_arguments)
        arguments.extend(policy.caller_arguments)
        return LaunchSpec(
            executable="claude",
            argv=("claude", *arguments),
            environment=child_environment,
        )
    except ProfileLaunchError:
        raise
    except Exception as exc:
        raise ProfileLaunchError("could not build isolated Claude launch") from exc


def _write_mcp_config(
    profile: ResolvedProfile,
    workspace: Path,
    environment: Mapping[str, str],
) -> Path:
    servers: dict[str, Any] = {}
    for item in profile.mcps:
        if not isinstance(item, Mapping):
            raise ValueError("MCP declarations must be mappings")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP declarations require a name")
        servers[name] = mcp_entry_for_harness(item, "claude", environment=environment)

    relative = Path("mcp.json")
    write_workspace_file(
        workspace,
        relative,
        json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2) + "\n",
    )
    return workspace / relative


def _write_settings(profile: ResolvedProfile, workspace: Path) -> Path | None:
    allow = launch_permission_rules(profile, "permissions_allow")
    deny = launch_permission_rules(profile, "permissions_deny")

    settings: dict[str, Any] = {}
    permissions: dict[str, list[str]] = {}
    if allow:
        permissions["allow"] = list(allow)
    if deny:
        permissions["deny"] = list(deny)
    if permissions:
        settings["permissions"] = permissions
    if profile.enabled_plugins:
        settings["enabledPlugins"] = dict(profile.enabled_plugins)
    if not settings:
        return None

    relative = Path("settings.json")
    write_workspace_file(
        workspace,
        relative,
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
    )
    return workspace / relative


def _write_skills_plugin(profile: ResolvedProfile, workspace: Path) -> Path | None:
    local_skills: list[tuple[str, Path]] = []
    for item in profile.skills:
        if not isinstance(item, Mapping):
            raise ValueError("skill declarations must be mappings")
        path_value = item.get("path")
        source_dir = item.get("_source_dir")
        if not path_value or not source_dir:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("local skills require a name")
        source = _resolve_source_path(source_dir, path_value)
        if source.is_dir():
            local_skills.append((name, source))

    if not local_skills:
        return None

    plugin_dir = workspace / "skills-plugin"
    write_workspace_file(
        workspace,
        Path("skills-plugin/.claude-plugin/plugin.json"),
        json.dumps(
            {
                "name": f"{profile.name}-skills",
                "description": f"Closed-world skills for the '{profile.name}' profile",
                "version": "0.0.0",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    for name, source in local_skills:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("local skills must not contain symbolic links")
            if not path.is_file():
                continue
            relative = Path("skills-plugin") / "skills" / name / path.relative_to(source)
            write_workspace_file(workspace, relative, path.read_bytes())
    return plugin_dir


def _system_prompt_path(profile: ResolvedProfile) -> Path:
    value = profile.system_prompt
    if not value:
        raise ValueError("system prompt is empty")
    declared = PurePosixPath(value)
    if declared.is_absolute() or ".." in declared.parts:
        prompt = Path(value)
        if not prompt.is_absolute():
            raise ValueError("system prompt path must be relative to the profile source")
        return _require_file(prompt)

    for source_dir in _source_dirs(profile):
        candidate = _resolve_source_path(source_dir, value)
        if candidate.is_file():
            return candidate
    raise ValueError("system prompt file was not found")


def _source_dirs(profile: ResolvedProfile) -> tuple[str, ...]:
    values: list[str] = []
    for section in _SECTIONS_WITH_SOURCE_DIR:
        for item in getattr(profile, section):
            source_dir = item.get("_source_dir") if isinstance(item, Mapping) else None
            if isinstance(source_dir, str) and source_dir not in values:
                values.append(source_dir)
    return tuple(values)


def _resolve_source_path(source_dir: object, value: object) -> Path:
    if not isinstance(source_dir, str) or not source_dir:
        raise ValueError("profile assets require an explicit source directory")
    if not isinstance(value, str) or not value:
        raise ValueError("profile asset paths must be strings")
    root = Path(source_dir).resolve(strict=True)
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("profile asset paths must stay within their source directory")
    candidate = (root / Path(*relative.parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("profile asset path escapes its source directory") from exc
    return candidate


def _require_file(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("system prompt path is not a file")
    return resolved
