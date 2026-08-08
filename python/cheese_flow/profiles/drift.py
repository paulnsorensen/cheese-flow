"""Deterministic drift calculation for compiled profile files."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .models import DriftRecord

_SENSITIVE_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "privatekey",
    "apikey",
    "accesstoken",
    "authorization",
    "bearer",
    "clientsecret",
    "clienttoken",
    "cookie",
    "session",
)
_SECRET_MAP_PREFIXES = ("env", "header", "auth", "credential")
_URL_KEY_NAMES = frozenset(
    {
        "databaseurl",
        "dburl",
        "databaseuri",
        "dburi",
        "connectionurl",
        "connectionuri",
        "dsn",
    }
)
_CREDENTIAL_URL_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,31}://[^/\s:@]+(?::[^/\s@]*)?@")
_ABSENT_FILE = object()


class DriftError(Exception):
    """A handled drift-computation failure."""


@dataclass(frozen=True)
class FileComparison:
    """One baseline/live/compiled comparison for a target-relative path."""

    target: str
    destination_path: PurePosixPath
    baseline: Path | None
    live: Path | None
    compiled: Path | None


def compute_drift(comparisons: Iterable[FileComparison]) -> list[DriftRecord]:
    """Return stable records for every differing leaf across three files."""
    records: list[DriftRecord] = []
    for comparison in comparisons:
        records.extend(_diff_file(comparison))
    records.sort(key=lambda record: _sort_key(record.target, record.destination_path, record.path))
    return records


def format_drift(records: Sequence[DriftRecord]) -> str:
    """Render drift grouped by target and destination path."""
    if not records:
        return ""
    ordered = sorted(
        records,
        key=lambda record: _sort_key(record.target, record.destination_path, record.path),
    )
    lines: list[str] = []
    current: tuple[str, str] | None = None
    for record in ordered:
        destination = record.destination_path.as_posix()
        group = (record.target, destination)
        if group != current:
            if current is not None:
                lines.append("")
            lines.append(f"{record.target}  {destination}")
            current = group
        lines.append(f"  {record.path or '(whole file)'}")
        lines.append(f"    baseline: {_render(record.baseline)}")
        lines.append(f"    live:     {_render(record.live)}")
        lines.append(f"    compiled: {_render(record.compiled)}")
    return "\n".join(lines) + "\n"


def _diff_file(comparison: FileComparison) -> list[DriftRecord]:
    destination = PurePosixPath(comparison.destination_path)
    is_json = destination.as_posix().endswith(".json")
    live = _read(comparison.live, is_json, live_destination=destination)
    if live is _ABSENT_FILE:
        return []

    baseline = _read(comparison.baseline, is_json)
    compiled = _read(comparison.compiled, is_json)
    baseline_leaves = _leaves(baseline)
    live_leaves = _leaves(live)
    compiled_leaves = _leaves(compiled)
    records: list[DriftRecord] = []
    for path in sorted(set(baseline_leaves) | set(live_leaves) | set(compiled_leaves)):
        values = (
            baseline_leaves.get(path),
            live_leaves.get(path),
            compiled_leaves.get(path),
        )
        if values[0] == values[1] == values[2]:
            continue
        safe_values = tuple(
            _redact_value(value, key=path, whole_file=not is_json) for value in values
        )
        records.append(
            DriftRecord(
                target=comparison.target,
                destination_path=destination,
                path=path,
                baseline=safe_values[0],
                live=safe_values[1],
                compiled=safe_values[2],
            )
        )
    return records


def _read(
    path: Path | None,
    is_json: bool,
    *,
    live_destination: PurePosixPath | None = None,
) -> Any:
    if path is None:
        return _ABSENT_FILE
    path = Path(path)
    if live_destination is not None:
        if not _validate_live_destination(path, live_destination):
            return _ABSENT_FILE
    elif not path.exists():
        return _ABSENT_FILE
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if is_json else text
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        kind = "JSON" if is_json else "text"
        raise DriftError(f"{path}: invalid {kind} content") from exc


def _validate_live_destination(path: Path, destination: PurePosixPath) -> bool:
    """Inspect a live destination lexically without following links."""
    destination = PurePosixPath(destination)
    if (
        destination.is_absolute()
        or not destination.parts
        or any(part in {".", ".."} for part in destination.parts)
    ):
        raise DriftError(f"{path}: live destination is outside its target root")
    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise DriftError(f"{path}: live destination is outside its target root")

    destination_parts = destination.parts
    if (
        len(path.parts) > len(destination_parts)
        and path.parts[-len(destination_parts) :] == destination_parts
    ):
        root = Path(*path.parts[: -len(destination_parts)])
        if not root.is_absolute() or path != root.joinpath(*destination_parts):
            raise DriftError(f"{path}: live destination is outside its target root")

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise DriftError(f"{path}: could not inspect live destination") from exc
        if stat.S_ISLNK(info.st_mode):
            raise DriftError(f"{path}: live destination contains a symlink boundary: {current}")
        if current == path:
            if not stat.S_ISREG(info.st_mode):
                raise DriftError(f"{path}: live destination is not a regular file")
        elif not stat.S_ISDIR(info.st_mode):
            raise DriftError(f"{path}: live destination parent is not a directory: {current}")
    return True


def _leaves(value: Any) -> dict[str, Any]:
    if value is _ABSENT_FILE:
        return {}
    out: dict[str, Any] = {}
    _walk(value, "", out)
    return out


def _walk(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, Mapping) and value:
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _walk(child, child_prefix, out)
        return
    out[prefix] = value


def _redact_value(
    value: Any,
    *,
    key: str | None = None,
    whole_file: bool = False,
) -> Any:
    if value is _ABSENT_FILE:
        return None
    if whole_file:
        raw = value.encode("utf-8") if isinstance(value, str) else _canonical_bytes(value)
        return {
            "redacted": True,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "length": len(raw),
        }
    if (key is not None and _is_sensitive_key(key)) or _is_credential_url(value):
        return {
            "redacted": True,
            "sha256": hashlib.sha256(_canonical_bytes(value)).hexdigest(),
        }
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_value(child, key=str(child_key))
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(child) for child in value]
    return value


def _is_credential_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if _CREDENTIAL_URL_RE.search(value):
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.username is not None or parsed.password is not None:
        return True
    secret_query_keys = {
        "auth",
        "authorization",
        "apikey",
        "accesskey",
        "credential",
        "credentials",
        "password",
        "passwd",
        "secret",
        "token",
        "user",
        "username",
    }
    return any(
        re.sub(r"[^a-z0-9]", "", key.lower()) in secret_query_keys
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _is_sensitive_key(key: str) -> bool:
    parts = tuple(re.sub(r"[^a-z0-9]", "", part.lower()) for part in key.split("."))
    if any(part.startswith(_SECRET_MAP_PREFIXES) for part in parts):
        return True
    terminal = parts[-1] if parts else ""
    return (
        any(marker in terminal for marker in _SENSITIVE_KEY_MARKERS) or terminal in _URL_KEY_NAMES
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(child) for child in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sort_key(target: str, destination: PurePosixPath, path: str) -> tuple[str, str, str]:
    return target, PurePosixPath(destination).as_posix(), path


def _render(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, ensure_ascii=False)


__all__ = ["DriftError", "FileComparison", "compute_drift", "format_drift"]
