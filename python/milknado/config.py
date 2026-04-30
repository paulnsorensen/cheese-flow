"""Project root resolution for milknado MCP tools.

Infrastructure consumed by the MCP shim — not a domain type, so it lives at
the package root rather than under ``domains/common``.
"""

from __future__ import annotations

import os
from pathlib import Path


def project_root(explicit: str | None) -> Path:
    """Resolve the milknado project root.

    Precedence: explicit argument > ``MILKNADO_PROJECT_ROOT`` env var > cwd.
    """
    if explicit and explicit.strip():
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("MILKNADO_PROJECT_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def graph_db_path(root: Path) -> Path:
    """Return the graph database path.

    ``MILKNADO_DB_PATH`` env var takes precedence so cheese-flow can relocate
    the SQLite db out of the worktree (see cheese-home spec). Falls back to the
    in-repo default when the env var is unset or blank.
    """
    override = os.environ.get("MILKNADO_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return root / ".milknado" / "milknado.db"
