"""Canonical JSON encoding for schema-v1 profile manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath
from typing import Any

from pydantic import BaseModel

from .models import CompiledProfileManifest


def _json_value(value: Any) -> Any:
    """Return a JSON-compatible value without changing collection order."""
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Encode ``value`` as deterministic, compact UTF-8 JSON bytes."""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def encode_manifest(manifest: CompiledProfileManifest) -> bytes:
    """Encode one validated profile manifest using canonical JSON."""
    if not isinstance(manifest, CompiledProfileManifest):
        manifest = CompiledProfileManifest.model_validate(manifest)
    return canonical_json_bytes(manifest.model_dump(mode="json"))


def decode_manifest(data: bytes | str | Mapping[str, object]) -> CompiledProfileManifest:
    """Decode canonical or ordinary JSON into a schema-v1 profile manifest."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, Mapping):
        raise TypeError("profile manifest must be a JSON object")
    return CompiledProfileManifest.model_validate(data)


def load_manifest(path: Path) -> CompiledProfileManifest:
    """Read and decode a profile manifest from ``path``."""
    return decode_manifest(Path(path).read_bytes())


__all__ = [
    "canonical_json_bytes",
    "decode_manifest",
    "encode_manifest",
    "load_manifest",
]
