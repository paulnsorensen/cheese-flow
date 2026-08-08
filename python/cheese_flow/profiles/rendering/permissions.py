"""Canonical profile permission parsing and projection helpers.

The profile format uses Claude's permission-rule spelling as the cross-harness
interlingua.  Harness renderers lower only the subset they understand, but all
of them share the same validation and MCP classification here.  Validation is
strict for structured ``Bash(...)`` and ``mcp__...`` rules: a malformed rule
raises before a renderer can start writing output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from cheese_flow.profiles.errors import ProfilePermissionsError


def render_codex_rules_file(
    rules: Sequence[tuple[Sequence[str], str]],
) -> str:
    """Serialize normalized Codex prefix rules deterministically."""

    lines = [
        "# Managed by cheese-flow — canonical cross-harness permission rules.",
        (
            "# Do not edit; regenerated on every profile compilation. "
            "The Codex-owned default.rules is untouched."
        ),
        "",
    ]
    for pattern, decision in rules:
        lines.extend(
            (
                "prefix_rule(",
                f"    pattern = [{', '.join(json.dumps(token) for token in pattern)}],",
                f"    decision = {json.dumps(decision)},",
                ")",
            )
        )
    return "\n".join(lines) + "\n"


_BASH_PREFIX_RE = re.compile(r"^Bash\((?P<command>.+):\*\)$")
_MCP_PREFIX = "mcp__"
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class PermissionRuleError(ProfilePermissionsError, ValueError):
    """Raised when a canonical permission rule or projection input is invalid."""


def _invalid(message: str) -> PermissionRuleError:
    return PermissionRuleError(f"invalid permission rule: {message}")


def _parse_mcp_rule_unchecked(rule: str) -> tuple[str, str] | None:
    if not rule.startswith(_MCP_PREFIX):
        return None
    rest = rule[len(_MCP_PREFIX) :]
    server, separator, tool = rest.partition("__")
    if not separator:
        raise _invalid("MCP rule must be mcp__<server>__<tool>")
    if not server or not tool:
        raise _invalid("MCP rule requires a non-empty server and tool")
    if _CONTROL_RE.search(server) or _CONTROL_RE.search(tool):
        raise _invalid("MCP server and tool names must not contain control characters")
    if any(char.isspace() for char in server + tool):
        raise _invalid("MCP server and tool names must not contain whitespace")
    if "*" in tool and tool != "*":
        raise _invalid("MCP wildcard is valid only as the complete tool name")
    return server, tool


def _validate_rule(rule: object) -> str:
    if not isinstance(rule, str):
        raise _invalid("rules must be strings")
    if not rule:
        raise _invalid("rule must not be empty")
    if rule != rule.strip():
        raise _invalid("rule must not have leading or trailing whitespace")
    if _CONTROL_RE.search(rule):
        raise _invalid("rule must not contain control characters")

    if rule.startswith("Bash("):
        match = _BASH_PREFIX_RE.fullmatch(rule)
        if match is None:
            raise _invalid("Bash rules must use Bash(<command>:*)")
        command = match.group("command")
        if not command or command != command.strip() or not command.split():
            raise _invalid("Bash prefix must contain a non-empty command")
    elif rule.startswith(_MCP_PREFIX):
        _parse_mcp_rule_unchecked(rule)

    return rule


def validate_permission_rule(rule: object) -> str:
    """Validate and return one canonical permission rule unchanged."""

    return _validate_rule(rule)


def validate_permission_rules(rules: Iterable[object]) -> tuple[str, ...]:
    """Validate a rule sequence before any renderer performs a write.

    The returned tuple preserves declaration order and duplicates.  Renderers
    decide their own channel precedence; this helper never sorts or merges
    caller input.
    """

    if isinstance(rules, (str, bytes, bytearray)):
        raise _invalid("rules must be a sequence of rule strings")
    try:
        return tuple(_validate_rule(rule) for rule in rules)
    except TypeError as exc:
        raise _invalid("rules must be an iterable of rule strings") from exc


_PERMISSION_FIELDS = frozenset({"permissions_allow", "permissions_deny"})


def _select_permission_rules(
    profile: Any,
    field: str,
    *,
    persistent: bool,
) -> tuple[str, ...]:
    if field not in _PERMISSION_FIELDS:
        raise _invalid(f"unsupported permission field {field!r}")

    if persistent:
        settings = getattr(profile, "settings", {})
        if settings is None:
            configured: object = ()
        elif not isinstance(settings, Mapping):
            raise _invalid("profile settings must be a mapping")
        else:
            configured = settings.get(field, ())
    else:
        configured = getattr(profile, field, ())

    if configured is None:
        return ()
    if isinstance(configured, (str, bytes, bytearray)):
        raise _invalid(f"{field} must be a sequence of permission rules")
    try:
        values = tuple(configured)
    except TypeError as exc:
        raise _invalid(f"{field} must be a sequence of permission rules") from exc
    return validate_permission_rules(values)


def persistent_permission_rules(profile: Any, field: str) -> tuple[str, ...]:
    """Select canonical rules persisted in compiled/project settings."""
    return _select_permission_rules(profile, field, persistent=True)


def launch_permission_rules(profile: Any, field: str) -> tuple[str, ...]:
    """Select canonical rules declared for one isolated launch."""
    return _select_permission_rules(profile, field, persistent=False)


def bash_argv(rule: str) -> list[str] | None:
    """Return argv-prefix tokens for ``Bash(<command>:*)`` rules.

    Non-Bash canonical rules return ``None``.  Structured malformed rules are
    rejected rather than silently skipped.
    """

    value = _validate_rule(rule)
    match = _BASH_PREFIX_RE.fullmatch(value)
    if match is None:
        return None
    tokens = match.group("command").split()
    return tokens or None


def parse_mcp_rule(rule: str) -> tuple[str, str] | None:
    """Return ``(server, tool)`` for an MCP rule, or ``None`` otherwise."""

    value = _validate_rule(rule)
    return _parse_mcp_rule_unchecked(value)


def named_mcp_tools(rules: Sequence[str]) -> dict[str, set[str]]:
    """Bucket named MCP tools by server, excluding whole-server ``*`` rules."""

    validated = validate_permission_rules(rules)
    out: dict[str, set[str]] = {}
    for rule in validated:
        parsed = _parse_mcp_rule_unchecked(rule)
        if parsed is None:
            continue
        server, tool = parsed
        if tool != "*":
            out.setdefault(server, set()).add(tool)
    return out


def whole_server_mcp_allows(rules: Sequence[str]) -> set[str]:
    """Collect servers allowed by a whole-server ``mcp__<server>__*`` rule."""

    validated = validate_permission_rules(rules)
    out: set[str] = set()
    for rule in validated:
        parsed = _parse_mcp_rule_unchecked(rule)
        if parsed is not None and parsed[1] == "*":
            out.add(parsed[0])
    return out


def _validate_server_plugins(server_plugins: Mapping[str, str]) -> None:
    if not isinstance(server_plugins, Mapping):
        raise _invalid("native MCP server plugins must be a mapping")
    for server, plugin in server_plugins.items():
        if not isinstance(server, str) or not server or server != server.strip():
            raise _invalid("native MCP server names must be non-empty strings")
        if not isinstance(plugin, str) or not plugin or plugin != plugin.strip():
            raise _invalid("native MCP plugin names must be non-empty strings")
        if _CONTROL_RE.search(server + plugin) or any(char.isspace() for char in server + plugin):
            raise _invalid("native MCP server and plugin names must not contain whitespace")


def native_mcp_server_plugins(
    native_plugins: Sequence[Mapping[str, Any]], harness: str
) -> dict[str, str]:
    """Map MCP server names to native plugin names for one harness."""

    if isinstance(native_plugins, (str, bytes, bytearray)):
        raise _invalid("native MCP plugins must be a sequence of mappings")
    if not isinstance(harness, str) or not harness or harness != harness.strip():
        raise _invalid("harness must be a non-empty string")

    flag = f"{harness}_native"
    out: dict[str, str] = {}
    try:
        entries = iter(native_plugins)
    except TypeError as exc:
        raise _invalid("native MCP plugins must be a sequence of mappings") from exc

    for entry in entries:
        if not isinstance(entry, Mapping):
            raise _invalid("native MCP plugin entries must be mappings")
        native = entry.get(flag, False)
        if not isinstance(native, bool):
            raise _invalid(f"{flag} must be a boolean")
        if not native:
            continue

        plugin = entry.get("name")
        servers = entry.get("servers") or ()
        if not isinstance(plugin, str) or not plugin or plugin != plugin.strip():
            raise _invalid("native MCP plugin name must be a non-empty string")
        if isinstance(servers, (str, bytes, bytearray)):
            raise _invalid("native MCP plugin servers must be a sequence")
        try:
            server_names = tuple(servers)
        except TypeError as exc:
            raise _invalid("native MCP plugin servers must be a sequence") from exc
        for server in server_names:
            if not isinstance(server, str) or not server or server != server.strip():
                raise _invalid("native MCP server names must be non-empty strings")
            if _CONTROL_RE.search(server + plugin) or any(
                char.isspace() for char in server + plugin
            ):
                raise _invalid("native MCP server and plugin names must not contain whitespace")
            out[server] = plugin

    return out


def rewrite_native_mcp_rule(rule: str, server_plugins: Mapping[str, str]) -> str:
    """Namespace one MCP rule when its server is provided by a native plugin."""

    _validate_server_plugins(server_plugins)
    value = _validate_rule(rule)
    parsed = _parse_mcp_rule_unchecked(value)
    if parsed is None:
        return value
    server, tool = parsed
    plugin = server_plugins.get(server)
    if plugin is None:
        return value
    return f"{_MCP_PREFIX}plugin_{plugin}_{server}__{tool}"


def rewrite_native_mcp_rules(rules: Sequence[str], server_plugins: Mapping[str, str]) -> list[str]:
    """Rewrite a rule sequence, preserving declaration order and duplicates."""

    _validate_server_plugins(server_plugins)
    return [rewrite_native_mcp_rule(rule, server_plugins) for rule in rules]


def _rewrite_allowed_tools_item(item: str, server_plugins: Mapping[str, str]) -> str:
    if not item:
        raise _invalid("allowed-tools entries must not be empty")
    return rewrite_native_mcp_rule(item, server_plugins)


def rewrite_skill_allowed_tools(text: str, server_plugins: Mapping[str, str]) -> str:
    """Rewrite MCP entries in a skill's leading ``allowed-tools`` frontmatter.

    Both the comma-separated inline form and the YAML block-list form are
    supported.  Every discovered entry is validated, even when no native MCP
    rewrite is needed.
    """

    if not isinstance(text, str):
        raise _invalid("skill content must be a string")
    _validate_server_plugins(server_plugins)
    if not text.startswith("---"):
        return text

    lines = text.splitlines(keepends=True)
    end = next(
        (index for index in range(1, len(lines)) if lines[index].rstrip("\n") == "---"),
        None,
    )
    if end is None:
        return text

    for index in range(1, end):
        bare = lines[index].rstrip("\n")
        inline = re.match(r"^allowed-tools:\s*(\S.*?)\s*$", bare)
        if inline:
            items = [item.strip() for item in inline.group(1).split(",")]
            rewritten = [_rewrite_allowed_tools_item(item, server_plugins) for item in items]
            trailing = "\n" if lines[index].endswith("\n") else ""
            lines[index] = "allowed-tools: " + ", ".join(rewritten) + trailing
            return "".join(lines)

        if re.match(r"^allowed-tools:\s*$", bare):
            for item_index in range(index + 1, end):
                item = re.match(r"^(\s*-\s*)(\S.*?)\s*$", lines[item_index].rstrip("\n"))
                if not item:
                    break
                trailing = "\n" if lines[item_index].endswith("\n") else ""
                rewritten = _rewrite_allowed_tools_item(item.group(2), server_plugins)
                lines[item_index] = item.group(1) + rewritten + trailing
            return "".join(lines)

    return text


__all__ = [
    "PermissionRuleError",
    "bash_argv",
    "launch_permission_rules",
    "named_mcp_tools",
    "native_mcp_server_plugins",
    "parse_mcp_rule",
    "persistent_permission_rules",
    "rewrite_native_mcp_rule",
    "rewrite_native_mcp_rules",
    "rewrite_skill_allowed_tools",
    "validate_permission_rule",
    "validate_permission_rules",
    "whole_server_mcp_allows",
]
