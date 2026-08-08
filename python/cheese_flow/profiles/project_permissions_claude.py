"""Plan Claude project permission settings replacements."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ProfilePermissionsError
from .parse import ResolvedProfile
from .rendering.permissions import persistent_permission_rules


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw) if raw.strip() else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfilePermissionsError(f"{path}: existing settings are not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProfilePermissionsError(f"{path}: existing settings must be a JSON object")
    return value


def _settings_permissions(settings: dict[str, Any], path: Path) -> dict[str, Any]:
    existing = settings.get("permissions")
    if existing is None:
        permissions: dict[str, Any] = {}
    elif isinstance(existing, Mapping):
        permissions = dict(existing)
    else:
        raise ProfilePermissionsError(f"{path}: settings.permissions must be a JSON object")
    settings["permissions"] = permissions
    return permissions


def plan_project_permissions(
    profile: ResolvedProfile,
    project_root: Path,
    *,
    local: bool,
) -> tuple[tuple[Path, bytes], ...]:
    """Return Claude's complete settings replacement without mutating the target."""
    allow = persistent_permission_rules(profile, "permissions_allow")
    deny = persistent_permission_rules(profile, "permissions_deny")
    filename = "settings.local.json" if local else "settings.json"
    settings_path = Path(project_root) / ".claude" / filename
    settings = _read_settings(settings_path)
    permissions = _settings_permissions(settings, settings_path)
    permissions["allow"] = list(allow)
    permissions["deny"] = list(deny)
    payload = (json.dumps(settings, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return ((settings_path, payload),)


__all__ = ["plan_project_permissions"]
