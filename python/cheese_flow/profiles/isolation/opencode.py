"""Build an isolated OpenCode launch from inline configuration."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.runtime import write_workspace_file
from cheese_flow.profiles.launch_policy import ValidatedLaunchPolicy
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.opencode import (
    _mcp_server_record,
    _translate_permission,
)
from cheese_flow.profiles.rendering.permissions import (
    PermissionRuleError,
    launch_permission_rules,
)

_PERMISSION_KEYS = {
    "Edit": "edit",
    "Write": "edit",
    "Read": "read",
    "Grep": "grep",
    "Glob": "glob",
    "Bash": "bash",
    "WebFetch": "webfetch",
    "WebSearch": "websearch",
    "Skill": "skill",
    "Agent": "task",
    "ExternalDirectory": "external_directory",
    "Lsp": "lsp",
    "LSP": "lsp",
}
_PRIVATE_ENV_DIRECTORIES = (
    ("HOME", Path("home")),
    ("XDG_CONFIG_HOME", Path("xdg-config")),
    ("XDG_DATA_HOME", Path("xdg-data")),
    ("XDG_CACHE_HOME", Path("xdg-cache")),
    ("XDG_STATE_HOME", Path("xdg-state")),
    ("OPENCODE_CONFIG_DIR", Path("opencode-config")),
)


def _private_environment(workspace: Path) -> dict[str, str]:
    protected: dict[str, str] = {}
    for name, relative in _PRIVATE_ENV_DIRECTORIES:
        path = workspace / relative
        if path.is_symlink():
            raise ValueError("OpenCode isolation paths must stay within the workspace")
        path.mkdir(mode=0o700, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("OpenCode isolation paths must be private directories")
        os.chmod(path, 0o700)
        protected[name] = str(path)
    return protected


def build_opencode_isolation(
    profile: ResolvedProfile,
    policy: ValidatedLaunchPolicy,
    workspace: Path,
    *,
    environment: Mapping[str, str],
) -> LaunchSpec:
    """Build the closed-world OpenCode launch and its environment snapshot."""
    try:
        if not isinstance(profile, ResolvedProfile):
            raise ValueError("isolated OpenCode launch requires a resolved profile")
        if not isinstance(policy, ValidatedLaunchPolicy):
            raise ValueError("isolated OpenCode launch requires a validated policy")
        if policy.harness != "opencode" or not policy.isolated:
            raise ValueError("OpenCode isolation requires an isolated OpenCode policy")
        if profile.enabled_plugins:
            raise ProfileLaunchError(
                "isolated OpenCode does not support enabled_plugins restrictions"
            )
        if profile.tools:
            raise ProfileLaunchError("isolated OpenCode does not support tools restrictions")
        if not isinstance(workspace, Path) or not workspace.is_dir() or workspace.is_symlink():
            raise ValueError("isolated OpenCode workspace is not a directory")
        if not isinstance(environment, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in environment.items()
        ):
            raise ValueError("OpenCode launch environment must contain string keys and values")

        child_environment = {**dict(environment), **dict(profile.env)}
        protected_environment = _private_environment(workspace)
        config_path = workspace / "opencode.json"
        protected_environment.update(
            {
                "OPENCODE_CONFIG": str(config_path),
                "OPENCODE_CONFIG_CONTENT": "",
                "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
                "OPENCODE_PERMISSION": "",
            }
        )
        config: dict[str, Any] = {
            "mcp": _mcp_config(
                profile,
                {**child_environment, **protected_environment},
            )
        }
        if profile.system_prompt is not None:
            config["instructions"] = [_system_prompt_path(profile)]
        config_content = json.dumps(config)
        write_workspace_file(workspace, Path("opencode.json"), config_content + "\n")

        launch_environment = {
            **child_environment,
            **protected_environment,
            "OPENCODE_CONFIG_CONTENT": config_content,
        }
        permission = _permission_config(profile)
        if permission:
            launch_environment["OPENCODE_PERMISSION"] = json.dumps(permission)
        else:
            launch_environment.pop("OPENCODE_PERMISSION", None)

        return LaunchSpec(
            executable="opencode",
            argv=("opencode", *policy.profile_arguments, *policy.caller_arguments),
            environment=launch_environment,
        )
    except ProfileLaunchError:
        raise
    except Exception as exc:
        raise ProfileLaunchError("could not build isolated OpenCode launch") from exc


def _mcp_config(
    profile: ResolvedProfile, environment: Mapping[str, str]
) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for item in profile.mcps:
        if not isinstance(item, Mapping):
            raise ValueError("MCP declarations must be mappings")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP declarations require a name")
        servers[name] = _mcp_server_record(item, environment)
    return servers


def _permission_config(profile: ResolvedProfile) -> dict[str, Any]:
    permission: dict[str, Any] = {}
    try:
        rules = launch_permission_rules(profile, "permissions_deny")
    except PermissionRuleError as exc:
        raise ProfileLaunchError(f"OpenCode permission deny is invalid: {exc}") from exc
    for rule in rules:
        key = _PERMISSION_KEYS.get(rule)
        if key is not None:
            permission[key] = "deny"
            continue
        structured_tool = rule.partition("(")[0]
        if rule.startswith(("Bash(", "mcp__")) or (
            rule.endswith(")") and structured_tool in _PERMISSION_KEYS
        ):
            translated_key, pattern = _translate_permission(rule)
            if pattern is None:
                permission[translated_key] = "deny"
                continue
            existing = permission.get(translated_key)
            if existing == "deny":
                continue
            if existing is None:
                existing = {}
                permission[translated_key] = existing
            if not isinstance(existing, dict):
                raise ProfileLaunchError(
                    f"OpenCode deny rule {rule!r} conflicts with a broader {translated_key!r} deny"
                )
            existing[pattern] = "deny"
            continue
        raise ProfileLaunchError(
            f"OpenCode cannot represent deny rule {rule!r}; use a supported tool, "
            "Bash(<command>:*), <tool>(<argument>), or mcp__<server>__<tool>"
        )
    return permission


def _system_prompt_path(profile: ResolvedProfile) -> str:
    value = profile.system_prompt
    if not isinstance(value, str) or not value:
        raise ValueError("system prompt must be a path")
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("system prompt must be an existing absolute file")
    return str(path)


__all__ = ["build_opencode_isolation"]
