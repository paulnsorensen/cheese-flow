"""Shared profile asset and body-path transformations.

Every source and destination root is supplied by the caller.  These helpers do
not inspect the current directory, HOME, or any profile-discovery location.
"""

from __future__ import annotations

import stat
from collections.abc import Mapping, MutableMapping, MutableSequence, MutableSet
from pathlib import Path, PurePosixPath
from typing import Any

_ClaimFingerprint = tuple[bytes, int]


def track_file(out_files: MutableSequence[str], relative_path: str) -> None:
    """Append a generated path once, retaining the caller's order."""

    if relative_path not in out_files:
        out_files.append(relative_path)


def claim_destination(
    claims: MutableSet[str] | MutableMapping[str, _ClaimFingerprint] | None,
    base: Path,
    destination: Path,
    *,
    content: bytes | None = None,
    mode: int | None = None,
) -> bool:
    """Claim one renderer-local output path before mutating the filesystem.

    Set-backed callers retain strict duplicate rejection.  Mapping-backed
    callers may explicitly deduplicate a path only when both the candidate
    bytes and output mode match the first claim.
    """

    if claims is None:
        return True
    try:
        relative = Path(destination).relative_to(Path(base)).as_posix()
    except ValueError as exc:
        raise ValueError("destination escapes output root") from exc
    if isinstance(claims, MutableMapping):
        if content is None or mode is None:
            if relative in claims:
                raise ValueError(
                    f"conflicting generated destination without byte+mode comparison: {relative}"
                )
            claims[relative] = (b"", -1)
            return True
        fingerprint = (content, stat.S_IMODE(mode))
        previous = claims.get(relative)
        if previous is not None:
            if previous != fingerprint:
                raise ValueError(f"conflicting generated destination: {relative}")
            return False
        claims[relative] = fingerprint
        return True
    if relative in claims:
        raise ValueError(f"conflicting generated destination: {relative}")
    claims.add(relative)
    return True


def _relative_parts(value: str, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal: {value!r}")
    return path.parts


def shared_asset_relpath(asset: str) -> str:
    """Map a profile ``shared_assets`` path to a harness-root-relative path.

    Registry entries conventionally start with ``agents/``; that source-only
    component is dropped while all deeper components are retained.
    """

    parts = _relative_parts(asset, label="shared asset")
    if len(parts) == 1:
        return parts[0]
    return PurePosixPath(*parts[1:]).as_posix()


def _explicit_source_dir(
    item: Mapping[str, Any],
    source_root: Path | None,
) -> Path:
    source = source_root if source_root is not None else item.get("_source_dir")
    if source is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(source)


def body_abs(
    item: Mapping[str, Any],
    body_key: str = "body_path",
    *,
    source_root: Path | None = None,
) -> Path | None:
    """Resolve an optional body path against an explicit source directory.

    A missing declaration is an optional body and returns ``None``.  A
    declared but missing or escaping body fails loudly so renderers cannot
    silently publish an incomplete agent/command.
    """

    body_rel = item.get(body_key) or ""
    if not body_rel:
        return None
    if not isinstance(body_rel, str):
        raise ValueError(f"{body_key} must be a relative path")
    parts = _relative_parts(body_rel, label=body_key)
    candidate = _explicit_source_dir(item, source_root).joinpath(*parts)
    if not candidate.is_file():
        raise FileNotFoundError(
            f"profile item {item.get('name', '?')!r} declares {body_key} "
            f"{body_rel!r}, but it does not resolve to a file"
        )
    return candidate


def copy_hook_shared_assets(
    hook: Mapping[str, Any],
    harness_root: Path,
    base: Path,
    out_files: MutableSequence[str],
    *,
    source_root: Path | None = None,
    claims: MutableSet[str] | MutableMapping[str, _ClaimFingerprint] | None = None,
) -> None:
    """Copy explicitly declared hook assets below a harness root.

    ``hook['_source_dir']`` is the resolved per-item source directory supplied
    by profile loading; callers may instead pass ``source_root`` explicitly.
    The destination is derived from the declared POSIX asset identity and each
    generated path is recorded once relative to ``base``.
    """

    assets = hook.get("shared_assets") or ()
    if not assets:
        return
    source = _explicit_source_dir(hook, source_root)
    harness_root = Path(harness_root)
    base = Path(base)
    for asset in assets:
        if not isinstance(asset, str):
            raise ValueError("shared asset entries must be strings")
        parts = _relative_parts(asset, label="shared asset")
        src = source.joinpath(*parts)
        if not src.is_file():
            raise FileNotFoundError(f"hook shared asset not found: {src}")
        relative = shared_asset_relpath(asset)
        destination = harness_root / PurePosixPath(relative)
        try:
            tracked = destination.relative_to(base).as_posix()
        except ValueError as exc:
            raise ValueError("harness asset destination escapes output root") from exc
        content = src.read_bytes()
        mode = stat.S_IMODE(src.stat().st_mode)
        if claim_destination(claims, base, destination, content=content, mode=mode):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(mode)
        track_file(out_files, tracked)


__all__ = [
    "body_abs",
    "claim_destination",
    "copy_hook_shared_assets",
    "shared_asset_relpath",
    "track_file",
]
