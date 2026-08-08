"""Plan Codex project permission replacements."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import ParseError

from cheese_flow.profiles.errors import ProfilePermissionsError
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.rendering.permissions import (
    bash_argv,
    named_mcp_tools,
    parse_mcp_rule,
    render_codex_rules_file,
    validate_permission_rules,
    whole_server_mcp_allows,
)

_RULES_REL = Path(".codex/rules/cheese-flow-canonical.rules")
_CONFIG_REL = Path(".codex/config.toml")


def _permission_rules(profile: ResolvedProfile, field: str) -> object:
    values = getattr(profile, field)
    if values:
        return values
    settings = profile.settings
    return settings.get(field, ()) if isinstance(settings, Mapping) else ()


def _collect_prefix_rules(
    allow: tuple[str, ...], deny: tuple[str, ...]
) -> list[tuple[list[str], str]]:
    rules: list[tuple[list[str], str]] = []
    for rule in sorted(allow):
        argv = bash_argv(rule)
        if argv:
            rules.append((argv, "allow"))
    for rule in sorted(deny):
        argv = bash_argv(rule)
        if argv:
            rules.append((argv, "forbidden"))
    return rules


def _collect_mcp_scopes(
    allow: tuple[str, ...], deny: tuple[str, ...]
) -> tuple[set[str], dict[str, tuple[set[str], set[str]]]]:
    enabled = named_mcp_tools(allow)
    disabled = named_mcp_tools(deny)
    for server in whole_server_mcp_allows(allow):
        enabled.pop(server, None)

    managed: set[str] = set()
    for rule in (*allow, *deny):
        parsed = parse_mcp_rule(rule)
        if parsed:
            managed.add(parsed[0])

    servers = set(enabled) | set(disabled)
    scopes = {
        server: (enabled.get(server, set()), disabled.get(server, set())) for server in servers
    }
    return managed, scopes


def _load_config(path: Path) -> Any:
    if path.exists() and not path.is_file():
        raise ProfilePermissionsError(f"{path}: config path is not a file")
    if not path.is_file():
        return tomlkit.document()
    try:
        text = path.read_text(encoding="utf-8")
        return tomlkit.parse(text) if text.strip() else tomlkit.document()
    except (OSError, UnicodeError, ParseError) as exc:
        raise ProfilePermissionsError(f"{path}: existing config is not valid TOML") from exc


def _plan_mcp_config(
    path: Path,
    managed: set[str],
    scopes: dict[str, tuple[set[str], set[str]]],
) -> tuple[Path, bytes] | None:
    if not managed:
        return None

    document = _load_config(path)
    servers = document.get("mcp_servers")
    if servers is not None and not isinstance(servers, MutableMapping):
        raise ProfilePermissionsError(f"{path}: mcp_servers must be a TOML table")

    changed = False
    for server in sorted(managed):
        entry = servers.get(server) if servers is not None else None
        if entry is not None and not isinstance(entry, MutableMapping):
            raise ProfilePermissionsError(f"{path}: mcp_servers.{server} must be a TOML table")

        enabled, disabled = scopes.get(server, (set(), set()))
        if entry is not None:
            for key in ("enabled_tools", "disabled_tools"):
                if key in entry:
                    del entry[key]
                    changed = True
            if len(entry) == 0:
                del servers[server]
                changed = True
                entry = None

        if not enabled and not disabled:
            continue
        if servers is None:
            servers = tomlkit.table()
            document["mcp_servers"] = servers
            changed = True
        if entry is None:
            entry = tomlkit.table()
            servers[server] = entry
            changed = True
        if enabled:
            entry["enabled_tools"] = sorted(enabled)
            changed = True
        if disabled:
            entry["disabled_tools"] = sorted(disabled)
            changed = True

    if servers is not None and len(servers) == 0:
        del document["mcp_servers"]
        changed = True
    if not changed:
        return None

    return path, tomlkit.dumps(document).encode("utf-8")


def plan_project_permissions(
    profile: ResolvedProfile,
    project_root: Path,
    *,
    local: bool,
) -> tuple[tuple[Path, bytes], ...]:
    """Return Codex permission replacements without mutating the project."""
    if local:
        return ()

    allow = validate_permission_rules(_permission_rules(profile, "permissions_allow"))
    deny = validate_permission_rules(_permission_rules(profile, "permissions_deny"))
    planned: list[tuple[Path, bytes]] = []

    prefix_rules = _collect_prefix_rules(allow, deny)
    planned.append(
        (
            Path(project_root) / _RULES_REL,
            render_codex_rules_file(prefix_rules).encode("utf-8"),
        )
    )

    managed, scopes = _collect_mcp_scopes(allow, deny)
    config = _plan_mcp_config(Path(project_root) / _CONFIG_REL, managed, scopes)
    if config is not None:
        planned.append(config)

    return tuple(planned)


__all__ = ["plan_project_permissions"]
