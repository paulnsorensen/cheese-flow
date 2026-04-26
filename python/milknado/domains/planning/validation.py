"""Dict-to-dataclass validation for milknado planning inputs.

Functions here cross the slice crust (used by the MCP shim), so they are
public — no leading underscore.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from .change import FileChange, NewRelationship, RelationshipReason, SymbolRef

_VALID_REASONS = frozenset({"new_file", "new_import", "new_call", "new_type_use"})


def _parse_symbol(i: int, s: object) -> SymbolRef:
    if not isinstance(s, dict):
        raise ValueError(f"symbols[{i}] must be a dict")
    name = s.get("name")
    file = s.get("file")
    if not isinstance(name, str) or not isinstance(file, str):
        raise ValueError(f"symbols[{i}] must have string 'name' and 'file'")
    return SymbolRef(name=name, file=file)


def dict_to_file_change(d: dict) -> FileChange:
    path = d["path"]
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError(f"path must be repo-relative without traversal, got {path!r}")
    raw_symbols = d.get("symbols") or []
    if not isinstance(raw_symbols, (list, tuple)):
        raise ValueError("symbols must be a list of dicts")
    symbols = tuple(_parse_symbol(i, s) for i, s in enumerate(raw_symbols))
    return FileChange(
        id=d["id"],
        path=path,
        edit_kind=d.get("edit_kind", "modify"),
        symbols=symbols,
        depends_on=tuple(d.get("depends_on", [])),
    )


def dict_to_new_relationship(d: dict) -> NewRelationship:
    reason = d["reason"]
    if not isinstance(reason, str):
        raise ValueError(f"reason must be a string, got {type(reason).__name__!r}")
    if reason not in _VALID_REASONS:
        raise ValueError(f"invalid reason: {reason!r}; expected one of {sorted(_VALID_REASONS)}")
    return NewRelationship(
        source_change_id=d["source_change_id"],
        dependant_change_id=d["dependant_change_id"],
        reason=cast(RelationshipReason, reason),
    )
