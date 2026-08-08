"""Render explicit profile data for OpenCode."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping, MutableSet, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.rendering.agents import (
    agent_is_read_only,
    serialize_frontmatter,
    strip_frontmatter,
)
from cheese_flow.profiles.rendering.assets import body_abs, claim_destination
from cheese_flow.profiles.rendering.permissions import persistent_permission_rules
from cheese_flow.profiles.rendering.template import render_mcp_for_harness

_OPENCODE = "opencode"
_MCP_DEFAULT = ("claude", "codex", "opencode")
_ITEM_DEFAULT = ("claude", "codex", "copilot", "crush", "cursor", "opencode")
_SCHEMA_STUB = {"$schema": "https://opencode.ai/config.json"}

# Claude ``Bash(<command>:*)`` prefix rules become OpenCode shell globs.
_BASH_PREFIX_RE = re.compile(r"^Bash\(([^:)]+):\*\)$")
_PAREN_RE = re.compile(r"^([A-Za-z]+)\((.*)\)$")
_ENV_REF_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

_TOOL_KEY = {
    "Bash": "bash",
    "Read": "read",
    "Edit": "edit",
    "Write": "edit",
    "WebFetch": "webfetch",
    "WebSearch": "websearch",
    "Glob": "glob",
    "Grep": "grep",
    "Skill": "skill",
    "Agent": "task",
    "ExternalDirectory": "external_directory",
    "Lsp": "lsp",
    "LSP": "lsp",
}
_MAP_TOOLS = frozenset(
    {"read", "edit", "glob", "grep", "bash", "task", "external_directory", "skill"}
)


def _selected(item: Mapping[str, Any], harness: str, defaults: Sequence[str]) -> bool:
    harnesses = item.get("harnesses")
    if harnesses is None:
        return harness in defaults
    if isinstance(harnesses, str):
        return harnesses == harness
    return harness in harnesses


def _name(value: Any, *, kind: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError(f"{kind} name must be a single non-empty path component")
    if "/" in value or "\\" in value:
        raise ValueError(f"{kind} name must be a single non-empty path component")
    return value


def _source_path(item: Mapping[str, Any], relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} must be a relative path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal: {relative!r}")
    source_dir = item.get("_source_dir")
    if source_dir is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(str(source_dir)).joinpath(*path.parts)


def _items(
    profile: ResolvedProfile, field: str, defaults: Sequence[str]
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        item
        for item in getattr(profile, field)
        if _selected(item, _OPENCODE, defaults) and not item.get("_from_opencode_native_plugin")
    )


def _translate_permission(rule: str) -> tuple[str, str | None]:
    """Classify one profile permission as an OpenCode key and optional pattern."""
    match = _BASH_PREFIX_RE.fullmatch(rule)
    if match:
        return "bash", f"{match.group(1)} *"

    if rule.startswith("mcp__"):
        server, separator, tool = rule[len("mcp__") :].partition("__")
        if not separator or tool in {"", "*"}:
            return f"{server}_*", None
        return f"{server}_{tool}", None

    match = _PAREN_RE.fullmatch(rule)
    if match:
        tool, argument = match.groups()
        key = _TOOL_KEY.get(tool)
        if key in _MAP_TOOLS:
            return key, argument
        if key is not None:
            return key, None
        return "bash", rule

    return "bash", rule


def _permission_rules(profile: ResolvedProfile, field: str) -> tuple[str, ...]:
    return persistent_permission_rules(profile, field)


def _apply_permissions(
    permission: dict[str, Any], rules: Sequence[tuple[str, str | None]], action: str
) -> None:
    for key, pattern in rules:
        if pattern is None:
            permission[key] = action
            continue
        bucket = permission.setdefault(key, {})
        if isinstance(bucket, dict):
            bucket[pattern] = action


def _to_opencode_env(value: str) -> str:
    return _ENV_REF_RE.sub(lambda match: f"{{env:{match.group(1) or match.group(2)}}}", value)


def _mcp_server_record(mcp: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    if mcp.get("url") or mcp.get("type") in {"http", "sse", "remote"}:
        raise ValueError(
            f"OpenCode MCP {mcp.get('name', '?')!r} does not support remote transports"
        )
    args = mcp.get("args")
    if args is not None and (
        isinstance(args, (str, bytes, bytearray)) or not isinstance(args, Sequence)
    ):
        raise ValueError(f"MCP {mcp.get('name', '<unnamed>')!r} args must be a sequence")
    env = mcp.get("env")
    if env is not None and not isinstance(env, Mapping):
        raise ValueError(f"MCP {mcp.get('name', '<unnamed>')!r} env must be a mapping")
    rendered = render_mcp_for_harness(mcp, _OPENCODE, environment=environment)
    command = rendered.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError(f"MCP {mcp.get('name', '<unnamed>')!r} is missing command")
    rendered_args = rendered.get("args")
    if rendered_args is None:
        args_list: list[Any] = []
    elif isinstance(rendered_args, list):
        args_list = rendered_args
    else:
        raise ValueError(f"MCP {mcp.get('name', '<unnamed>')!r} args must be a sequence")
    record: dict[str, Any] = {
        "type": "local",
        "enabled": True,
        "command": [command, *args_list],
    }
    rendered_env = rendered.get("env")
    if rendered_env is not None:
        if not isinstance(rendered_env, Mapping):
            raise ValueError(f"MCP {mcp.get('name', '<unnamed>')!r} env must be a mapping")
        record["environment"] = {
            str(key): _to_opencode_env(str(value)) for key, value in rendered_env.items()
        }
    return record


def _validate_mcp_transports(profile: ResolvedProfile) -> None:
    for mcp in _items(profile, "mcps", _MCP_DEFAULT):
        if mcp.get("url") or mcp.get("type") in {"http", "sse", "remote"}:
            raise ValueError(
                f"OpenCode MCP {mcp.get('name', '?')!r} does not support remote transports"
            )


class OpencodeRenderer:
    """Render OpenCode agents, skills, MCPs, and permissions."""

    name = _OPENCODE
    mcp_default = _MCP_DEFAULT

    def render(
        self, profile: ResolvedProfile, target: Path, *, logical_root: Path
    ) -> tuple[PurePosixPath, ...]:
        del logical_root
        if profile.isolated:
            _permission_rules(profile, "permissions_allow")
            _permission_rules(profile, "permissions_deny")
            _validate_mcp_transports(profile)
        target.mkdir(parents=True, exist_ok=True)
        claims: set[str] = set()
        written: list[PurePosixPath] = []
        written.extend(self._render_agents(profile, target, claims))
        written.extend(self._render_skills(profile, target, claims))

        if profile.isolated:
            written.extend(self._render_config(profile, target, claims))

        return tuple(sorted(set(written), key=lambda path: path.as_posix()))

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        del profile, overlay
        return LaunchSpec(
            executable=_OPENCODE,
            argv=(_OPENCODE, *arguments),
            environment=dict(environment),
        )

    def _render_agents(
        self,
        profile: ResolvedProfile,
        target: Path,
        claims: MutableSet[str],
    ) -> list[PurePosixPath]:
        written: list[PurePosixPath] = []
        for item in _items(profile, "agents", _ITEM_DEFAULT):
            body_path = body_abs(item, "body_path")
            if body_path is None:
                continue
            name = _name(item.get("name"), kind="agent")
            if not body_path.is_file():
                raise FileNotFoundError(f"agent body not found: {body_path}")

            metadata: dict[str, Any] = {}
            description = item.get("description")
            if description:
                metadata["description"] = str(description)
            metadata["mode"] = "subagent"
            model = (item.get("models") or {}).get(_OPENCODE) or ""
            if model and model != "inherit":
                metadata["model"] = str(model)
            if agent_is_read_only(item):
                metadata["permission"] = {"edit": "deny"}

            body = strip_frontmatter(body_path.read_text(encoding="utf-8"))
            relative = PurePosixPath("agents") / f"{name}.md"
            destination = target.joinpath(*relative.parts)
            claim_destination(claims, target, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                f"---\n{serialize_frontmatter(metadata)}\n---\n{body}",
                encoding="utf-8",
            )
            written.append(relative)
        return written

    def _render_skills(
        self,
        profile: ResolvedProfile,
        target: Path,
        claims: MutableSet[str],
    ) -> list[PurePosixPath]:
        written: list[PurePosixPath] = []
        for item in _items(profile, "skills", _ITEM_DEFAULT):
            relative_path = item.get("path") or ""
            if not relative_path:
                continue
            name = _name(item.get("name"), kind="skill")
            source = _source_path(item, relative_path, label="skill path")
            if not source.is_dir():
                raise FileNotFoundError(f"skill directory not found: {source}")

            relative = PurePosixPath("skills") / name
            destination = target.joinpath(*relative.parts)
            claim_destination(claims, target, destination)
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            written.extend(
                relative / child.relative_to(source)
                for child in sorted(source.rglob("*"))
                if child.is_file()
            )
        return written

    def _render_config(
        self,
        profile: ResolvedProfile,
        target: Path,
        claims: MutableSet[str],
    ) -> list[PurePosixPath]:
        mcps = _items(profile, "mcps", _MCP_DEFAULT)
        allow = tuple(
            _translate_permission(rule) for rule in _permission_rules(profile, "permissions_allow")
        )
        deny = tuple(
            _translate_permission(rule) for rule in _permission_rules(profile, "permissions_deny")
        )
        if not mcps and not allow and not deny:
            return []

        config_path = target / "opencode.json"
        if config_path.is_file():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"could not read OpenCode config {config_path}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"OpenCode config {config_path} must contain a JSON object")
        else:
            data = dict(_SCHEMA_STUB)

        if mcps:
            mcp_section = data.setdefault("mcp", {})
            if not isinstance(mcp_section, dict):
                raise ValueError("OpenCode config field 'mcp' must be a JSON object")
            for mcp in mcps:
                name = _name(mcp.get("name"), kind="MCP")
                mcp_section[name] = _mcp_server_record(
                    mcp,
                    profile.template_environment or profile.env,
                )

        if allow or deny:
            permission = data.setdefault("permission", {})
            if not isinstance(permission, dict):
                raise ValueError("OpenCode config field 'permission' must be a JSON object")
            _apply_permissions(permission, allow, "allow")
            _apply_permissions(permission, deny, "deny")

        claim_destination(claims, target, config_path)
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return [PurePosixPath("opencode.json")]


__all__ = ["OpencodeRenderer"]
