"""Reading MCP entries out of a harness's own user-scope config file.

Adapters verify registration by reading the native config directly rather than
asking a harness CLI, so a postcondition never depends on a command that may not
exist. Claude Code and Cursor store JSON under ``mcpServers``; Codex stores TOML
under ``[mcp_servers.<name>]``.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from cheese_flow.models import HarnessName


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


def has_allowed_mcp_server(path: Path, server: str) -> bool:
    """Return whether Claude Code may invoke every tool exposed by a server."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    permissions = document.get("permissions")
    if not isinstance(permissions, dict):
        return False
    allow = permissions.get("allow")
    return isinstance(allow, list) and f"mcp__{server}" in allow
