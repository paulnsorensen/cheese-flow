"""TOML validation and atomic persistence of the cheese-flow manifest."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cheese_flow.models import (
    COMPONENT_NAMES,
    HARNESS_NAMES,
    DesiredState,
    RepositorySelection,
)

_TOP_LEVEL_KEYS = ("harnesses", "components", "repositories")
_REPOSITORY_KEYS = ("search_roots", "max_depth", "selected")


class ManifestError(Exception):
    """A manifest is missing, unparseable, or does not describe a valid desired state."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def default_config_path() -> Path:
    """Return ``$XDG_CONFIG_HOME/cheese/config.toml`` (``~/.config`` fallback)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cheese" / "config.toml"


def load_desired_state(path: Path) -> DesiredState:
    """Parse and validate the manifest at ``path``.

    Unknown keys or names, relative paths, duplicates, missing required
    components, and selections outside the search roots are validation errors.
    """
    document = _read_document(path)
    _reject_unknown_keys(path, document.keys(), _TOP_LEVEL_KEYS, "top-level keys")

    harnesses = _string_list(path, document, "harnesses")
    components = _string_list(path, document, "components")
    _reject_unknown_names(path, harnesses, HARNESS_NAMES, "harness names")
    _reject_unknown_names(path, components, COMPONENT_NAMES, "component names")

    state = _build_state(path, harnesses, components, _repositories(path, document))
    _reject_inconsistent_selection(path, state.repositories)
    return state


def save_desired_state(state: DesiredState, path: Path) -> None:
    """Write ``state`` to ``path`` atomically, replacing any existing manifest."""
    text = _render_toml(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _read_document(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise ManifestError(path, "manifest not found") from error
    except OSError as error:
        raise ManifestError(path, f"manifest is unreadable: {error.strerror}") from error
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ManifestError(path, "manifest is not valid UTF-8") from error
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(path, f"invalid TOML: {error}") from error


def _reject_unknown_keys(path: Path, keys: Any, allowed: tuple[str, ...], label: str) -> None:
    unknown = [key for key in keys if key not in allowed]
    if unknown:
        raise ManifestError(path, f"unknown {label}: {', '.join(sorted(unknown))}")


def _reject_unknown_names(
    path: Path, values: list[str], allowed: tuple[str, ...], label: str
) -> None:
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ManifestError(
            path,
            f"unknown {label}: {', '.join(unknown)} (supported: {', '.join(allowed)})",
        )


def _string_list(
    path: Path, table: dict[str, Any], key: str, *, required: bool = True
) -> list[str]:
    if key not in table:
        if required:
            raise ManifestError(path, f"missing required key: {key}")
        return []
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(path, f"{key} must be an array of strings")
    return value


def _repositories(path: Path, document: dict[str, Any]) -> dict[str, Any]:
    table = document.get("repositories", {})
    if not isinstance(table, dict):
        raise ManifestError(path, "repositories must be a table")
    _reject_unknown_keys(path, table.keys(), _REPOSITORY_KEYS, "keys in [repositories]")

    fields: dict[str, Any] = {
        "search_roots": tuple(
            Path(item) for item in _string_list(path, table, "search_roots", required=False)
        ),
        "selected": tuple(
            Path(item) for item in _string_list(path, table, "selected", required=False)
        ),
    }
    if "max_depth" in table:
        max_depth = table["max_depth"]
        if not isinstance(max_depth, int) or isinstance(max_depth, bool):
            raise ManifestError(path, "max_depth must be an integer")
        fields["max_depth"] = max_depth
    return fields


def _build_state(
    path: Path, harnesses: list[str], components: list[str], repositories: dict[str, Any]
) -> DesiredState:
    try:
        return DesiredState(
            harnesses=tuple(harnesses),
            components=tuple(components),
            repositories=RepositorySelection(**repositories),
        )
    except ValidationError as error:
        raise ManifestError(path, _describe(error)) from error


def _describe(error: ValidationError) -> str:
    return "; ".join(detail["msg"].removeprefix("Value error, ") for detail in error.errors())


def _reject_inconsistent_selection(path: Path, repositories: RepositorySelection) -> None:
    orphans = [
        str(selected)
        for selected in repositories.selected
        if not any(selected.is_relative_to(root) for root in repositories.search_roots)
    ]
    if orphans:
        raise ManifestError(
            path, f"selected repositories are not under any search root: {', '.join(orphans)}"
        )


def _render_toml(state: DesiredState) -> str:
    lines = [
        f"harnesses = {_array(state.harnesses)}",
        f"components = {_array(state.components)}",
        "",
        "[repositories]",
        f"search_roots = {_array(str(p) for p in state.repositories.search_roots)}",
        f"max_depth = {state.repositories.max_depth}",
        f"selected = {_array(str(p) for p in state.repositories.selected)}",
    ]
    return "\n".join(lines) + "\n"


def _array(values: Any) -> str:
    return "[" + ", ".join(_string(value) for value in values) + "]"


def _string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    for raw, encoded in (("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        escaped = escaped.replace(raw, encoded)
    return f'"{escaped}"'
