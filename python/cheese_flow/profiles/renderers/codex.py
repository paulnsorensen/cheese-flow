"""Codex profile rendering from resolved, explicit inputs."""

from __future__ import annotations

import json
import shlex
import shutil
from collections.abc import Mapping, MutableSequence
from pathlib import Path, PurePosixPath
from typing import Any

import tomlkit

from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.rendering.agents import agent_is_read_only, strip_frontmatter
from cheese_flow.profiles.rendering.assets import (
    body_abs,
    claim_destination,
    copy_hook_shared_assets,
    track_file,
)
from cheese_flow.profiles.rendering.permissions import (
    bash_argv,
    named_mcp_tools,
    parse_mcp_rule,
    persistent_permission_rules,
    render_codex_rules_file,
    whole_server_mcp_allows,
)
from cheese_flow.profiles.rendering.template import render_mcp_for_harness
from cheese_flow.profiles.source import ResolvedProfile

_CODEX_MCP_DEFAULT = ("claude", "codex")
_AGENT_DEFAULT = ("claude", "codex", "opencode", "cursor", "copilot", "crush")
_SKILL_DEFAULT = _AGENT_DEFAULT
_HOOK_DEFAULT = ("claude",)
_RULES_REL = PurePosixPath(".codex/rules/cheese-flow-canonical.rules")


class CodexRenderer:
    """Render Codex's profile-owned files under an explicit target root."""

    name = "codex"
    mcp_default = _CODEX_MCP_DEFAULT

    def render(
        self,
        profile: ResolvedProfile,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        target = Path(target)
        generated: list[str] = []
        claims: dict[str, tuple[bytes, int]] = {}
        self._write_agents(profile, target, generated)
        self._write_skills(profile, target, generated)
        self._write_hooks(profile, target, logical_root, generated, claims)
        if profile.isolated:
            self._write_mcps(profile, target)
        self._write_rules(profile, target, generated)
        if profile.isolated:
            self._write_mcp_tool_scopes(profile, target)
        return tuple(PurePosixPath(path) for path in generated)

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        """Project the base Codex executable without applying isolation."""
        del profile, overlay
        return LaunchSpec(
            executable="codex",
            argv=("codex", *arguments),
            environment=dict(environment),
        )

    def _write_agents(
        self,
        profile: ResolvedProfile,
        target: Path,
        generated: MutableSequence[str],
    ) -> None:
        for item in _items_for(profile.agents, "codex", _AGENT_DEFAULT):
            if item.get("_from_codex_native_plugin"):
                continue
            name = _single_component(item.get("name"), "agent name")
            body_path = body_abs(item)
            body = strip_frontmatter(body_path.read_text() if body_path else "")
            models = item.get("models") or {}
            if not isinstance(models, Mapping):
                raise ValueError("agent models must be a mapping")

            document = tomlkit.document()
            document["name"] = name
            document["description"] = str(item.get("description") or "")
            model = models.get("codex")
            if model:
                document["model"] = str(model)
            if agent_is_read_only(item):
                document["sandbox_mode"] = "read-only"
            document["developer_instructions"] = tomlkit.string(body, multiline=True)

            relative = PurePosixPath(".codex", "agents", f"{name}.toml")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(tomlkit.dumps(document))
            track_file(generated, relative.as_posix())

    def _write_skills(
        self,
        profile: ResolvedProfile,
        target: Path,
        generated: MutableSequence[str],
    ) -> None:
        for item in _items_for(profile.skills, "codex", _SKILL_DEFAULT):
            if item.get("_from_codex_native_plugin"):
                continue
            declared = item.get("path") or ""
            if not declared:
                continue
            name = _single_component(item.get("name"), "skill name")
            source = _explicit_path(item, declared, "skill path")
            if not source.is_dir():
                raise FileNotFoundError(f"skill source directory was not found: {source}")
            destination = target / ".agents" / "skills" / name
            if destination.exists():
                if destination.is_symlink() or not destination.is_dir():
                    raise ValueError(f"skill destination is not a directory: {destination}")
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            track_file(generated, PurePosixPath(".agents", "skills", name).as_posix())

    def _write_hooks(
        self,
        profile: ResolvedProfile,
        target: Path,
        logical_root: Path,
        generated: MutableSequence[str],
        claims: dict[str, tuple[bytes, int]],
    ) -> None:
        hooks = tuple(_items_for(profile.hooks, "codex", _HOOK_DEFAULT))
        if not hooks:
            return

        hook_groups: dict[str, list[dict[str, object]]] = {}
        for item in hooks:
            event = str(item.get("event") or "")
            if not event:
                raise ValueError("codex hook requires an event")
            matcher = item.get("matcher") or ""
            script = item.get("script") or ""
            command = item.get("command") or ""
            if script and command:
                raise ValueError(f"codex hook event {event!r} sets both script and command")
            if script:
                source = _explicit_path(item, script, "hook script")
                if not source.is_file():
                    raise FileNotFoundError(f"codex hook script was not found: {source}")
                relative = PurePosixPath(".codex", "hooks", Path(script).name)
                destination = target / relative
                content = source.read_bytes()
                mode = 0o755
                if claim_destination(
                    claims,
                    target,
                    destination,
                    content=content,
                    mode=mode,
                ):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    destination.chmod(mode)
                track_file(generated, relative.as_posix())
                command = f"bash {shlex.quote(str(logical_root / relative))}"
            elif not command:
                raise ValueError(f"codex hook event {event!r} has neither script nor command")
            copy_hook_shared_assets(
                item,
                target / ".codex",
                target,
                generated,
                claims=claims,
            )

            handler: dict[str, object] = {"type": "command", "command": str(command)}
            timeout = item.get("timeout")
            if timeout not in (None, ""):
                handler["timeout"] = int(timeout)
            group: dict[str, object] = {"hooks": [handler]}
            if matcher:
                group["matcher"] = str(matcher)
            hook_groups.setdefault(event, []).append(group)

        relative = PurePosixPath(".codex", "hooks.json")
        destination = target / relative
        payload = json.dumps({"hooks": hook_groups}, indent=2) + "\n"
        if claim_destination(
            claims,
            target,
            destination,
            content=payload.encode(),
            mode=0o644,
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload)
        track_file(generated, relative.as_posix())

    def _write_mcps(self, profile: ResolvedProfile, target: Path) -> None:
        mcps = tuple(_items_for(profile.mcps, "codex", _CODEX_MCP_DEFAULT))
        if not mcps:
            return
        config = target / ".codex" / "config.toml"
        document = _load_toml(config)
        servers = document.get("mcp_servers")
        if servers is None:
            servers = tomlkit.table()
            document["mcp_servers"] = servers
        for item in mcps:
            entry = _mcp_entry(item, profile.template_environment or profile.env)
            servers[str(item["name"])] = entry
        _dump_toml(config, document)

    def _write_rules(
        self,
        profile: ResolvedProfile,
        target: Path,
        generated: MutableSequence[str],
    ) -> None:
        rules = _collect_prefix_rules(profile)
        destination = target / _RULES_REL
        if not rules:
            if destination.is_file():
                destination.unlink()
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_codex_rules_file(rules))
        track_file(generated, _RULES_REL.as_posix())

    def _write_mcp_tool_scopes(self, profile: ResolvedProfile, target: Path) -> None:
        managed = _managed_mcp_servers(profile)
        if not managed:
            return
        scopes = _collect_mcp_tool_scopes(profile)
        config = target / ".codex" / "config.toml"
        document = _load_toml(config)
        servers = document.get("mcp_servers")

        for server in sorted(managed):
            entry = servers.get(server) if servers is not None else None
            enabled, disabled = scopes.get(server, (set(), set()))
            if entry is not None:
                for key in ("enabled_tools", "disabled_tools"):
                    if key in entry:
                        del entry[key]
                if len(entry) == 0:
                    del servers[server]
                    entry = None
            if not enabled and not disabled:
                continue
            if servers is None:
                servers = tomlkit.table()
                document["mcp_servers"] = servers
            if entry is None:
                entry = tomlkit.table()
                servers[server] = entry
            if enabled:
                entry["enabled_tools"] = sorted(enabled)
            if disabled:
                entry["disabled_tools"] = sorted(disabled)

        if servers is not None and len(servers) == 0:
            del document["mcp_servers"]
        if len(document) == 0:
            if config.is_file():
                config.unlink()
            return
        _dump_toml(config, document)


def _items_for(
    items: tuple[Mapping[str, Any], ...],
    harness: str,
    default: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    selected: list[Mapping[str, Any]] = []
    for item in items:
        harnesses = item.get("harnesses")
        members = (
            default
            if harnesses is None
            else (harnesses,)
            if isinstance(harnesses, str)
            else tuple(harnesses)
        )
        if harness in members:
            selected.append(item)
    return tuple(selected)


def _single_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"{label} must be one relative path component")
    return value


def _explicit_path(item: Mapping[str, Any], declared: object, label: str) -> Path:
    if not isinstance(declared, str) or not declared:
        raise ValueError(f"{label} must be a non-empty relative path")
    relative = PurePosixPath(declared)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label} must be relative and contain no traversal")
    source_root = item.get("_source_dir")
    if source_root is None:
        raise ValueError(f"{label} requires an explicit source root")
    return Path(source_root).joinpath(*relative.parts)


def _load_toml(path: Path) -> Any:
    if not path.is_file():
        return tomlkit.document()
    return tomlkit.parse(path.read_text())


def _dump_toml(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(document))


def _mcp_entry(item: Mapping[str, Any], environment: Mapping[str, str]) -> Any:
    materialized = dict(item)
    args = item.get("args")
    if args is not None:
        materialized["args"] = list(args) if not isinstance(args, str) else args
    env = item.get("env")
    if isinstance(env, Mapping):
        materialized["env"] = dict(env)
    rendered = render_mcp_for_harness(materialized, "codex", environment=environment)

    entry = tomlkit.table()
    if rendered.get("url") or rendered.get("type") in {"http", "sse"}:
        entry["type"] = str(rendered.get("type") or "http")
        entry["url"] = str(rendered["url"])
        if rendered.get("headers") is not None:
            entry["headers"] = rendered["headers"]
        return entry

    command = rendered.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError(f"Codex MCP {item.get('name', '?')!r} requires command or url")
    entry["command"] = command
    if rendered.get("args") is not None:
        entry["args"] = rendered["args"]
    env = rendered.get("env")
    if isinstance(env, Mapping) and env:
        values = tomlkit.table()
        for key, value in env.items():
            values[str(key)] = value
        entry["env"] = values
    return entry


def _permission_rules(profile: ResolvedProfile, field: str) -> tuple[str, ...]:
    return persistent_permission_rules(profile, field)


def _collect_prefix_rules(profile: ResolvedProfile) -> list[tuple[list[str], str]]:
    out: list[tuple[list[str], str]] = []
    for rule in sorted(_permission_rules(profile, "permissions_allow")):
        argv = bash_argv(rule)
        if argv:
            out.append((argv, "allow"))
    for rule in sorted(_permission_rules(profile, "permissions_deny")):
        argv = bash_argv(rule)
        if argv:
            out.append((argv, "forbidden"))
    return out


def _collect_mcp_tool_scopes(
    profile: ResolvedProfile,
) -> dict[str, tuple[set[str], set[str]]]:
    enabled = named_mcp_tools(_permission_rules(profile, "permissions_allow"))
    disabled = named_mcp_tools(_permission_rules(profile, "permissions_deny"))
    for server in whole_server_mcp_allows(_permission_rules(profile, "permissions_allow")):
        enabled.pop(server, None)
    servers = set(enabled) | set(disabled)
    return {server: (enabled.get(server, set()), disabled.get(server, set())) for server in servers}


def _managed_mcp_servers(profile: ResolvedProfile) -> set[str]:
    managed: set[str] = set()
    for field in ("permissions_allow", "permissions_deny"):
        for rule in _permission_rules(profile, field):
            parsed = parse_mcp_rule(rule)
            if parsed:
                managed.add(parsed[0])
    return managed


__all__ = ["CodexRenderer"]
