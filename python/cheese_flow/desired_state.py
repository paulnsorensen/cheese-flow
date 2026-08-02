"""TOML validation and atomic persistence of the cheese-flow manifest."""

from __future__ import annotations

import os
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cheese_flow.models import (
    COMPONENT_NAMES,
    HARNESS_NAMES,
    DesiredState,
    RepositorySelection,
    canonicalize,
)
from cheese_flow.repositories import is_repository


class ManifestError(Exception):
    """A manifest is missing, unparseable, or does not describe a valid desired state."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


class OptionError(Exception):
    """Command-line options do not describe a valid desired state."""


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
    _reject_non_integer_max_depth(path, document)
    return _build_state(path, document)


def state_from_options(
    harnesses: Sequence[str],
    components: Sequence[str],
    repositories: Sequence[Path],
) -> DesiredState:
    """Build a validated desired state from command-line options, not a manifest.

    Repository paths are resolved against the working directory, so a caller may
    name one relatively; each selection's parent becomes its search root, which
    is the narrowest root that satisfies the selection-under-a-root rule.

    A path that is not a git repository is rejected here, before planning: the
    installer can only index repositories, so accepting one would buy nothing
    but a blocked step in the middle of an otherwise applied run.
    """
    selected = tuple(dict.fromkeys(canonicalize(path) for path in repositories))
    strangers = [str(path) for path in selected if not is_repository(path)]
    if strangers:
        raise OptionError(f"not a git repository: {', '.join(strangers)}")
    search_roots = tuple(dict.fromkeys(path.parent for path in selected))
    try:
        return DesiredState(
            harnesses=tuple(harnesses),
            components=tuple(components),
            repositories=RepositorySelection(search_roots=search_roots, selected=selected),
        )
    except ValidationError as error:
        raise OptionError(_describe(error)) from error


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


def _reject_non_integer_max_depth(path: Path, document: dict[str, Any]) -> None:
    """Reject ``max_depth`` bool/str values pydantic's lax mode would silently coerce."""
    repositories = document.get("repositories")
    if not isinstance(repositories, dict) or "max_depth" not in repositories:
        return
    max_depth = repositories["max_depth"]
    if not isinstance(max_depth, int) or isinstance(max_depth, bool):
        raise ManifestError(path, "max_depth must be an integer")


def _build_state(path: Path, document: dict[str, Any]) -> DesiredState:
    try:
        return DesiredState(**document)
    except ValidationError as error:
        raise ManifestError(path, _describe(error)) from error


def _describe(error: ValidationError) -> str:
    errors = error.errors()
    parts: list[str] = []
    reported: set[str] = set()

    def add(key: str, message: str) -> None:
        if key not in reported:
            reported.add(key)
            parts.append(message)

    for detail in errors:
        loc = detail["loc"]
        kind = detail["type"]

        if kind == "extra_forbidden" and len(loc) == 1:
            keys = sorted(
                str(d["loc"][0])
                for d in errors
                if d["type"] == "extra_forbidden" and len(d["loc"]) == 1
            )
            add("top_level_extra", f"unknown top-level keys: {', '.join(keys)}")
        elif kind == "extra_forbidden" and len(loc) == 2 and loc[0] == "repositories":
            keys = sorted(
                str(d["loc"][1])
                for d in errors
                if d["type"] == "extra_forbidden"
                and len(d["loc"]) == 2
                and d["loc"][0] == "repositories"
            )
            add("repositories_extra", f"unknown keys in [repositories]: {', '.join(keys)}")
        elif kind == "literal_error" and loc and loc[0] in ("harnesses", "components"):
            field = loc[0]
            bad = [
                str(d["input"])
                for d in errors
                if d["type"] == "literal_error" and d["loc"] and d["loc"][0] == field
            ]
            allowed = HARNESS_NAMES if field == "harnesses" else COMPONENT_NAMES
            label = "harness names" if field == "harnesses" else "component names"
            add(
                f"literal_{field}",
                f"unknown {label}: {', '.join(bad)} (supported: {', '.join(allowed)})",
            )
        elif kind == "missing" and len(loc) == 1:
            add(f"missing_{loc[0]}", f"missing required key: {loc[0]}")
        elif kind == "model_type" and loc == ("repositories",):
            add("repositories_type", "repositories must be a table")
        elif kind == "greater_than_equal":
            field = loc[-1] if loc else ""
            add(f"ge_{field}", f"{field} must be >= {detail['ctx']['ge']}")
        elif kind == "tuple_type":
            field = loc[-1] if loc else ""
            add(f"array_{field}", f"{field} must be an array of strings")
        elif kind == "path_type" and len(loc) >= 2:
            field = loc[-2]
            add(f"array_{field}", f"{field} must be an array of strings")
        else:
            parts.append(detail["msg"].removeprefix("Value error, "))

    return "; ".join(parts)


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
