"""Deterministic Claude profile rendering.

The renderer owns only the generated Claude plugin tree and the cross-harness
shared agent/skill paths below the caller-provided target.  It deliberately
never discovers profile data, dotfiles, installed plugins, or process
configuration.  All source paths are carried by resolved profile items.
"""

from __future__ import annotations

import json
import shutil
import stat
from collections.abc import Mapping, MutableSequence, MutableSet, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from cheese_flow.profiles.models import LaunchSpec

from ..parse import ResolvedProfile
from ..rendering.agents import (
    claude_agent_frontmatter,
    item_harnesses,
    serialize_frontmatter,
    write_shared_claude_agent,
)
from ..rendering.assets import body_abs, claim_destination, copy_hook_shared_assets, track_file
from ..rendering.permissions import (
    native_mcp_server_plugins,
    rewrite_native_mcp_rules,
    rewrite_skill_allowed_tools,
    validate_permission_rules,
)
from ..rendering.template import mcp_entry_for_harness

_MCP_DEFAULT = ("claude", "codex", "opencode")
_ITEM_DEFAULT = ("claude", "codex", "copilot", "crush", "cursor", "opencode")
_HOOK_DEFAULT = ("claude",)
_MATCHER_EVENTS = frozenset({"PreToolUse", "PostToolUse"})


def _safe_name(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind} name must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"{kind} name must be a single relative path component: {value!r}")
    return value


def _selected(item: Mapping[str, Any], default: Sequence[str]) -> bool:
    return "claude" in item_harnesses(item, default)


def _source_path(item: Mapping[str, Any], relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} must be a relative path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal: {relative!r}")
    source_dir = item.get("_source_dir")
    if source_dir is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(source_dir).joinpath(*path.parts)


def _track_path(out: MutableSequence[str], target: Path, path: Path) -> None:
    try:
        relative = path.relative_to(target).as_posix()
    except ValueError as exc:
        raise ValueError(f"generated Claude path escapes target: {path}") from exc
    track_file(out, relative)


def _write_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    target: Path,
    claims: MutableSet[str],
) -> None:
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    claim_destination(claims, target, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _write_local_settings(
    profile: ResolvedProfile,
    target: Path,
    out: MutableSequence[str],
    claims: MutableSet[str],
) -> None:
    """Project explicit Claude marketplace and enabled-plugin declarations."""

    marketplaces = dict(profile.marketplaces)
    enabled = dict(profile.enabled_plugins)
    for plugin in profile.native_plugins:
        if not plugin.get("claude_native"):
            continue
        plugin_name = _safe_name(plugin.get("name"), kind="native plugin")
        marketplace_name = plugin.get("marketplace_name")
        marketplace_root = plugin.get("marketplace_root") or plugin.get("path")
        if not isinstance(marketplace_name, str) or not marketplace_name:
            raise ValueError(f"native plugin {plugin_name!r} requires marketplace_name")
        if not isinstance(marketplace_root, str) or not marketplace_root:
            raise ValueError(f"native plugin {plugin_name!r} requires marketplace_root")
        previous = marketplaces.get(marketplace_name)
        if previous is not None and previous != marketplace_root:
            raise ValueError(
                f"marketplace {marketplace_name!r} has conflicting roots "
                f"{previous!r} and {marketplace_root!r}"
            )
        marketplaces[marketplace_name] = marketplace_root
        enabled[f"{plugin_name}@{marketplace_name}"] = True
    if not marketplaces and not enabled:
        return

    settings_path = target / ".claude" / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Claude settings are not valid JSON: {settings_path}") from exc
        if not isinstance(loaded, Mapping):
            raise ValueError(f"Claude settings must be a JSON object: {settings_path}")
        settings.update(loaded)
    settings["extraKnownMarketplaces"] = {
        name: {"source": {"source": "directory", "path": path}}
        for name, path in sorted(marketplaces.items())
    }
    settings["enabledPlugins"] = {name: value for name, value in sorted(enabled.items()) if value}
    _write_json(settings_path, settings, target=target, claims=claims)
    _track_path(out, target, settings_path)


def _permissions(profile: ResolvedProfile, server_plugins: Mapping[str, str]) -> dict[str, Any]:
    settings = profile.settings
    configured_allow = settings.get("permissions_allow") if isinstance(settings, Mapping) else None
    configured_deny = settings.get("permissions_deny") if isinstance(settings, Mapping) else None
    allow_values = profile.permissions_allow if configured_allow is None else configured_allow
    deny_values = profile.permissions_deny if configured_deny is None else configured_deny
    allow = rewrite_native_mcp_rules(validate_permission_rules(allow_values), server_plugins)
    deny = rewrite_native_mcp_rules(validate_permission_rules(deny_values), server_plugins)
    permissions: dict[str, Any] = {}
    if allow:
        permissions["allow"] = allow
    if deny:
        permissions["deny"] = deny
    return permissions


def _copy_skill(
    target: Path,
    item: Mapping[str, Any],
    out: MutableSequence[str],
    server_plugins: Mapping[str, str],
    claims: MutableSet[str],
) -> None:
    name = _safe_name(item.get("name"), kind="skill")
    relative = item.get("path") or ""
    if not relative:
        return
    source = _source_path(item, relative, label="skill path")
    if not source.is_dir():
        return
    destination = target / ".claude" / "skills" / name
    claim_destination(claims, target, destination)
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    shutil.copytree(source, destination)
    if server_plugins:
        skill_md = destination / "SKILL.md"
        if skill_md.is_file():
            original = skill_md.read_text(encoding="utf-8")
            rewritten = rewrite_skill_allowed_tools(original, server_plugins)
            if rewritten != original:
                skill_md.write_text(rewritten, encoding="utf-8")
    _track_path(out, target, destination)


def _write_commands(
    profile: ResolvedProfile,
    plugin_dir: Path,
    target: Path,
    out: MutableSequence[str],
    claims: MutableSet[str],
) -> None:
    for item in profile.commands:
        if item.get("_from_native_plugin") or not _selected(item, _ITEM_DEFAULT):
            continue
        name = _safe_name(item.get("name"), kind="command")
        description = str(item.get("description") or "")
        models = item.get("models") or {}
        if not isinstance(models, Mapping):
            raise ValueError("command models must be a mapping")
        model = str(models.get("claude") or "")
        metadata: dict[str, str] = {}
        if description:
            metadata["description"] = description
        if model:
            metadata["model"] = model
        content = ""
        if metadata:
            content = f"---\n{serialize_frontmatter(metadata)}\n---\n"
        body = body_abs(item)
        if body is not None:
            content += body.read_text(encoding="utf-8")
        destination = plugin_dir / "commands" / f"{name}.md"
        claim_destination(claims, target, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        _track_path(out, target, destination)


def _write_hooks(
    profile: ResolvedProfile,
    plugin_dir: Path,
    target: Path,
    out: MutableSequence[str],
    claims: MutableSet[str],
) -> dict[str, list[dict[str, Any]]]:
    entries: dict[str, list[dict[str, Any]]] = {}
    for item in profile.hooks:
        if not _selected(item, _HOOK_DEFAULT):
            continue
        event = item.get("event")
        if not isinstance(event, str) or not event:
            raise ValueError("Claude hook event must be a non-empty string")
        script = item.get("script") or ""
        command = item.get("command") or ""
        if script and command:
            raise ValueError(f"Claude hook event {event!r} sets both 'script' and 'command'")
        if script:
            source = _source_path(item, script, label="hook script")
            if not source.is_file():
                raise FileNotFoundError(f"Claude hook script not found: {source}")
            basename = _safe_name(Path(script).name, kind="hook script")
            destination = plugin_dir / "hooks" / basename
            claim_destination(claims, target, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(
                destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            _track_path(out, target, destination)
            copy_hook_shared_assets(item, plugin_dir, target, out, claims=claims)
            command_value = f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{basename}"
        elif command:
            command_value = str(command)
        else:
            raise ValueError(f"Claude hook event {event!r} has neither 'script' nor 'command'")

        inner: dict[str, Any] = {"type": "command", "command": command_value}
        for key in ("timeout", "async"):
            if item.get(key) is not None:
                inner[key] = item[key]
        entry: dict[str, Any] = {"hooks": [inner]}
        matcher = item.get("matcher") or ""
        if matcher and event in _MATCHER_EVENTS:
            entry = {"matcher": str(matcher), "hooks": [inner]}
        entries.setdefault(event, []).append(entry)
    return entries


class ClaudeRenderer:
    """Render one resolved profile into a Claude-local plugin projection."""

    name = "claude"

    def render(
        self,
        profile: ResolvedProfile,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        """Write only profile-owned files below ``target``.

        ``logical_root`` is part of the renderer seam for callers that need a
        symbolic root; this Claude projection has no path-bearing templates,
        so it is intentionally not consulted or resolved.
        """

        del logical_root
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        plugin_dir = (
            target / ".claude" / "plugins" / "local" / _safe_name(profile.name, kind="profile")
        )
        plugin_dir.mkdir(parents=True, exist_ok=True)
        out: list[str] = []
        claims: set[str] = set()
        _write_local_settings(profile, target, out, claims)

        server_plugins = native_mcp_server_plugins(profile.native_plugins, "claude")
        permissions = _permissions(profile, server_plugins)

        if profile.mcp_scope != "user":
            servers: dict[str, Any] = {}
            for item in profile.mcps:
                if item.get("_from_native_plugin") or not _selected(item, _MCP_DEFAULT):
                    continue
                name = _safe_name(item.get("name"), kind="MCP")
                servers[name] = mcp_entry_for_harness(
                    item,
                    "claude",
                    environment=profile.template_environment or profile.env,
                )
            if servers:
                mcp_path = plugin_dir / ".mcp.json"
                _write_json(
                    mcp_path,
                    {"mcpServers": servers},
                    target=target,
                    claims=claims,
                )
                _track_path(out, target, mcp_path)

        for item in profile.agents:
            if item.get("_from_native_plugin") or not _selected(item, _ITEM_DEFAULT):
                continue
            name = _safe_name(item.get("name"), kind="agent")
            body = body_abs(item)
            if body is None:
                raise ValueError(f"Claude agent {name!r} has no body_path")
            write_shared_claude_agent(
                target,
                name,
                body,
                claude_agent_frontmatter(item),
                out,
                claims=claims,
            )

        for item in profile.skills:
            if item.get("_from_native_plugin") or not _selected(item, _ITEM_DEFAULT):
                continue
            _copy_skill(target, item, out, server_plugins, claims)

        _write_commands(profile, plugin_dir, target, out, claims)
        hooks = _write_hooks(profile, plugin_dir, target, out, claims)

        settings_path = plugin_dir / "settings.json"
        if permissions:
            _write_json(
                settings_path,
                {"permissions": permissions},
                target=target,
                claims=claims,
            )
            _track_path(out, target, settings_path)

        manifest: dict[str, Any] = {
            "name": profile.name,
            "version": "1.0.0",
            "description": profile.description,
        }
        if hooks:
            manifest["hooks"] = hooks
        for manifest_path in (
            plugin_dir / "plugin.json",
            plugin_dir / ".claude-plugin" / "plugin.json",
        ):
            _write_json(manifest_path, manifest, target=target, claims=claims)
            _track_path(out, target, manifest_path)

        _track_path(out, target, plugin_dir)
        return tuple(PurePosixPath(path) for path in out)

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        """Build Claude's base executable projection.

        Isolation policy flags and profile environment are applied by the
        launch-policy/isolation owner.  This method deliberately treats the
        overlay as an opaque explicit handle and performs no filesystem lookup.
        """

        del profile, overlay
        return LaunchSpec(
            executable="claude",
            argv=("claude", *arguments),
            environment=dict(environment),
        )


__all__ = ["ClaudeRenderer"]
