"""Read and declare harness-native MCP configuration.

Adapters inspect config directly so postconditions never depend on a harness CLI
that may not exist. Claude Code and Cursor store JSON; Codex stores TOML.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from cheese_flow.models import ConfigEdit, HarnessName


def read_mcp_entry(path: Path, harness: HarnessName, server: str) -> Any:
    """Return ``server``'s MCP entry in ``path``, or ``None`` if it is not there."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        if harness == "codex":
            return tomllib.loads(raw.decode()).get("mcp_servers", {}).get(server)
        document = json.loads(raw)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    servers = document.get("mcpServers")
    return servers.get(server) if isinstance(servers, dict) else None


def mcp_entry_holds(edit: ConfigEdit, harness: HarnessName, server: str) -> bool:
    """Whether ``harness``'s MCP config declares ``server`` exactly as ``edit`` says.

    A direct ``mcpServers`` entry is verified by its launch command and args, not
    by the config file merely mentioning the server — a stale entry pointing at a
    different binary must not satisfy the step that declared this one.
    """
    if not isinstance(edit.value, dict):
        raise ValueError(f"{server} MCP edit carries no entry mapping")
    entry = read_mcp_entry(edit.target, harness, server)
    if not isinstance(entry, dict):
        return False
    return entry.get("command") == edit.value["command"] and entry.get("args") == edit.value["args"]


def claude_config_dir() -> Path:
    """Claude's user config directory, including its documented override."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def codex_config_dir() -> Path:
    """Codex's user config directory, including its documented override."""
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def mcp_permission_edit(
    harness: HarnessName,
    server: str,
    *,
    claude_server: str | None = None,
    codex_plugin: str | None = None,
) -> ConfigEdit:
    """Declare the native server-wide MCP approval for one supported harness."""
    if harness == "claude-code":
        return ConfigEdit(
            target=claude_config_dir() / "settings.json",
            pointer="permissions.allow",
            value=f"mcp__{claude_server or server}__*",
            mode="append_unique",
        )
    if harness == "codex":
        prefix = f"plugins.{codex_plugin}.mcp_servers" if codex_plugin else "mcp_servers"
        return ConfigEdit(
            target=codex_config_dir() / "config.toml",
            pointer=f"{prefix}.{server}.default_tools_approval_mode",
            value="approve",
            mode="toml_set",
        )
    return ConfigEdit(
        target=Path.home() / ".cursor/cli-config.json",
        pointer="permissions.allow",
        value=f"Mcp({server}:*)",
        mode="append_unique",
    )


def config_edit_holds(edit: ConfigEdit) -> bool:
    """Return whether the declared target contains the declared value."""
    try:
        if edit.mode == "toml_set":
            document: Any = tomllib.loads(edit.target.read_text(encoding="utf-8"))
        else:
            document = json.loads(edit.target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
        return False

    current = document
    for key in edit.pointer.split("."):
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    if edit.mode == "append_unique":
        return isinstance(current, list) and edit.value in current
    return current == edit.value
