"""Deterministic Copilot profile rendering."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.rendering.agents import serialize_frontmatter, strip_frontmatter
from cheese_flow.profiles.rendering.assets import (
    body_abs,
    claim_destination,
    copy_hook_shared_assets,
    track_file,
)
from cheese_flow.profiles.rendering.permissions import (
    bash_argv,
    named_mcp_tools,
    native_mcp_server_plugins,
    parse_mcp_rule,
    rewrite_native_mcp_rules,
    whole_server_mcp_allows,
)
from cheese_flow.profiles.rendering.template import render_mcp_for_harness

if TYPE_CHECKING:
    from cheese_flow.profiles.parse import ResolvedProfile


_COPILOT_MCP_DEFAULT = ("claude", "codex")
_COPILOT_HOOK_DEFAULT = ("claude",)
_POLICY_FLAGS = ("--allow-tool", "--deny-tool")
_COPILOT_AGENT_PUBLIC_KEYS = frozenset(
    {
        "name",
        "description",
        "tools",
        "disallowedTools",
        "skills",
        "color",
        "effort",
        "maxTurns",
        "metadata",
    }
)
_COPILOT_HOOK_PUBLIC_KEYS = frozenset(
    {
        "name",
        "event",
        "matcher",
        "script",
        "command",
        "timeout",
        "async",
        "disabled",
        "optional",
    }
)


def _includes_harness(item: Mapping[str, Any], harness: str, default: tuple[str, ...]) -> bool:
    memberships = item.get("harnesses")
    if memberships is None:
        return harness in default
    if isinstance(memberships, (str, bytes)):
        raise ValueError("harnesses must be a sequence")
    return harness in memberships


def _items_for(
    items: Sequence[Mapping[str, Any]], harness: str, default: tuple[str, ...]
) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in items if _includes_harness(item, harness, default))


def _name_component(item: Mapping[str, Any], field: str = "name") -> str:
    name = item.get(field)
    if not isinstance(name, str) or not name:
        raise ValueError(f"{field} must be a non-empty name")
    path = PurePosixPath(name)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"{field} must be a single relative path component")
    return name


def _declared_path(item: Mapping[str, Any], field: str) -> Path:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{field} must be a relative path without traversal")
    source = item.get("_source_dir")
    if source is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(source).joinpath(*relative.parts)


def _public_projection(
    values: Mapping[str, Any],
    allowed: frozenset[str],
) -> dict[str, Any]:
    return {str(key): _public_value(value) for key, value in values.items() if str(key) in allowed}


def _public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _rendered_mcp(item: Mapping[str, Any], environment: Mapping[str, str]) -> Mapping[str, Any]:
    candidate = dict(item)
    args = candidate.get("args")
    if isinstance(args, (list, tuple)):
        candidate["args"] = list(args)
    env = candidate.get("env")
    if isinstance(env, Mapping):
        candidate["env"] = dict(env)
    return render_mcp_for_harness(candidate, "copilot", environment=environment)


def _mcp_entry(
    mcp: Mapping[str, Any], named: Mapping[str, set[str]], whole: set[str]
) -> dict[str, Any]:
    if mcp.get("url") or mcp.get("type") in {"http", "sse"}:
        url = mcp.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("Copilot MCP HTTP/SSE entries require a URL")
        entry: dict[str, Any] = {"type": mcp.get("type") or "http", "url": url}
        if mcp.get("headers") is not None:
            entry["headers"] = _json_value(mcp["headers"])
    else:
        command = mcp.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError("Copilot stdio MCP entries require a command")
        entry = {"command": command, "args": _json_value(mcp.get("args") or [])}
        if mcp.get("env") is not None:
            entry["env"] = _json_value(mcp["env"])

    name = mcp.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("MCP entries require a non-empty name")
    tools = named.get(name)
    entry["tools"] = ["*"] if name in whole or not tools else sorted(tools)
    return entry


def _flags_for(rules: Sequence[str], option: str) -> tuple[str, ...]:
    flags: list[str] = []
    for rule in sorted(rules):
        bash = bash_argv(rule)
        if bash is not None:
            flags.append(f"{option}=shell({' '.join(bash)})")
            continue
        parsed = parse_mcp_rule(rule)
        if parsed is None:
            continue
        server, tool = parsed
        spec = server if tool == "*" else f"{server}({tool})"
        flags.append(f"{option}={spec}")
    return tuple(flags)


def _launch_flags(profile: ResolvedProfile) -> tuple[str, ...]:
    server_plugins = native_mcp_server_plugins(profile.native_plugins, "copilot")
    allow = rewrite_native_mcp_rules(profile.permissions_allow, server_plugins)
    deny = rewrite_native_mcp_rules(profile.permissions_deny, server_plugins)
    return _flags_for(allow, "--allow-tool") + _flags_for(deny, "--deny-tool")


def _caller_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
    try:
        values = tuple(arguments)
    except TypeError as exc:
        raise ValueError("launch arguments must be a sequence") from exc
    if any(not isinstance(value, str) for value in values):
        raise ValueError("launch arguments must be strings")
    for value in values:
        if value in _POLICY_FLAGS or value.startswith(("--allow-tool=", "--deny-tool=")):
            raise ValueError(
                "Copilot launch policy flags must be declared by the profile, not the caller"
            )
    return values


def _read_mcp_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {}
    if not path.is_file():
        raise ValueError(f"Copilot MCP config is not a regular file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Copilot MCP config must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Copilot MCP config must be a JSON object")
    servers = data.get("mcpServers", {})
    if servers is None:
        servers = {}
    if not isinstance(servers, dict):
        raise ValueError("Copilot MCP config mcpServers must be an object")
    return dict(data), dict(servers)


def _mcp_names(items: Sequence[Mapping[str, Any]]) -> set[str]:
    return {name for item in items if isinstance(name := item.get("name"), str) and name}


class CopilotRenderer:
    """Render resolved profile data into Copilot's project surfaces."""

    name = "copilot"

    def render(
        self,
        profile: ResolvedProfile,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        base = Path(target)
        out: list[str] = []
        claims: dict[str, tuple[bytes, int]] = {}
        self._write_agents(profile, base, out)
        self._write_skills(profile, base, out)
        self._write_hooks(profile, base, out, claims)
        if profile.isolated:
            self._write_mcp(profile, base, out)
        return tuple(PurePosixPath(path) for path in out)

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        del overlay
        caller_arguments = _caller_arguments(arguments)
        return LaunchSpec(
            executable=self.name,
            argv=(self.name, *_launch_flags(profile), *caller_arguments),
            environment=environment,
        )

    def _write_agents(self, profile: ResolvedProfile, base: Path, out: list[str]) -> None:
        for agent in _items_for(
            profile.agents, self.name, ("claude", "codex", "opencode", "cursor", "copilot")
        ):
            if agent.get("_from_copilot_native_plugin"):
                continue
            name = _name_component(agent)
            path = base / ".github" / "agents" / f"{name}.agent.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            metadata = _public_projection(agent, _COPILOT_AGENT_PUBLIC_KEYS)
            parts = ["---\n", serialize_frontmatter(metadata), "\n---\n\n"]
            body = body_abs(agent)
            if body is not None:
                parts.append(strip_frontmatter(body.read_text(encoding="utf-8")))
            path.write_text("".join(parts), encoding="utf-8")
            track_file(out, f".github/agents/{name}.agent.md")

    def _write_skills(self, profile: ResolvedProfile, base: Path, out: list[str]) -> None:
        for skill in _items_for(
            profile.skills, self.name, ("claude", "codex", "opencode", "cursor", "copilot")
        ):
            if skill.get("_from_copilot_native_plugin"):
                continue
            relative = skill.get("path") or ""
            if not relative:
                continue
            source = _declared_path(skill, "path")
            if not source.is_dir():
                continue
            name = _name_component(skill)
            destination = base / ".github" / "skills" / name
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            track_file(out, f".github/skills/{name}")

    def _write_hooks(
        self,
        profile: ResolvedProfile,
        base: Path,
        out: list[str],
        claims: dict[str, tuple[bytes, int]],
    ) -> None:
        for hook in _items_for(profile.hooks, self.name, _COPILOT_HOOK_DEFAULT):
            script = hook.get("script")
            if not isinstance(script, str) or not script:
                raise ValueError("Copilot hook is missing 'script'")
            source = _declared_path(hook, "script")
            if not source.is_file():
                raise FileNotFoundError(f"Copilot hook script not found: {source}")
            script_name = PurePosixPath(script).name
            destination = base / ".github" / "hooks" / script_name
            content = source.read_bytes()
            if claim_destination(
                claims,
                base,
                destination,
                content=content,
                mode=0o755,
            ):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o755)
            script_relative = f".github/hooks/{script_name}"
            track_file(out, script_relative)
            copy_hook_shared_assets(
                hook,
                base / ".github" / "hooks",
                base,
                out,
                claims=claims,
            )

            hook_name = script_name.rsplit(".", 1)[0]
            payload = _public_projection(hook, _COPILOT_HOOK_PUBLIC_KEYS)
            payload["script"] = script_relative
            json_relative = f".github/hooks/{hook_name}.json"
            json_payload = json.dumps(payload, indent=2) + "\n"
            json_destination = base / json_relative
            if claim_destination(
                claims,
                base,
                json_destination,
                content=json_payload.encode(),
                mode=0o644,
            ):
                json_destination.parent.mkdir(parents=True, exist_ok=True)
                json_destination.write_text(json_payload, encoding="utf-8")
            track_file(out, json_relative)

    def _write_mcp(self, profile: ResolvedProfile, base: Path, out: list[str]) -> None:
        mcps = _items_for(profile.mcps, self.name, _COPILOT_MCP_DEFAULT)
        path = base / ".copilot" / "mcp-config.json"
        existing, servers = _read_mcp_config(path)
        before = dict(existing)
        named = named_mcp_tools(profile.permissions_allow)
        whole = whole_server_mcp_allows(profile.permissions_allow)
        owned_names = _mcp_names(profile.mcps)
        selected_names: set[str] = set()
        for raw in mcps:
            mcp = _rendered_mcp(raw, profile.template_environment or profile.env)
            name = mcp.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("MCP entries require a non-empty name")
            selected_names.add(name)
            servers[name] = _mcp_entry(mcp, named, whole)
        for name in owned_names - selected_names:
            servers.pop(name, None)
        if servers:
            existing["mcpServers"] = servers
        else:
            existing.pop("mcpServers", None)
        if existing == before:
            return
        if not existing:
            if path.is_file():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        track_file(out, ".copilot/mcp-config.json")


__all__ = ["CopilotRenderer"]
