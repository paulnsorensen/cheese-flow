"""Content-addressed generation publication for profile manifests."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .manifest_codec import canonical_json_bytes, encode_manifest
from .models import (
    CompiledFile,
    CompiledProfileManifest,
    CompileTarget,
    DriftRecord,
)

_GENERATIONS = PurePosixPath("generations")


def generation_descriptor(
    *,
    schema_version: int,
    profile: str,
    source_id: str,
    compile_targets: tuple[CompileTarget, ...],
    files: tuple[CompiledFile, ...],
    drift: tuple[DriftRecord, ...],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "profile": profile,
        "source_id": source_id,
        "compile_targets": [target.model_dump(mode="json") for target in compile_targets],
        "files": [compiled_file.model_dump(mode="json") for compiled_file in files],
        "drift": [record.model_dump(mode="json") for record in drift],
    }


def compute_generation(descriptor: Mapping[str, Any]) -> str:
    payload = dict(descriptor)
    if "generation" in payload:
        raise ValueError("descriptor must not contain generation")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def bind_generation(descriptor: Mapping[str, Any]) -> CompiledProfileManifest:
    payload = dict(descriptor)
    generation = compute_generation(payload)
    files = []
    for raw_file in payload["files"]:
        compiled_file = dict(raw_file)
        relative = PurePosixPath(compiled_file["fragment_path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError(f"invalid descriptor fragment path: {relative}")
        compiled_file["fragment_path"] = (_GENERATIONS / generation / relative).as_posix()
        files.append(compiled_file)
    payload["files"] = files
    return CompiledProfileManifest(generation=generation, **payload)


def validate_generation_binding(manifest: CompiledProfileManifest) -> CompiledProfileManifest:
    payload = manifest.model_dump(mode="json", exclude_none=False)
    generation = payload.pop("generation")
    prefix = _GENERATIONS / generation
    files = []
    for raw_file in payload["files"]:
        compiled_file = dict(raw_file)
        fragment = PurePosixPath(compiled_file["fragment_path"])
        if fragment.parts[: len(prefix.parts)] != prefix.parts:
            raise ValueError(f"fragment path {fragment} must start with generations/{generation}/")
        relative_parts = fragment.parts[len(prefix.parts) :]
        if not relative_parts:
            raise ValueError(f"fragment path {fragment} has no generation-relative suffix")
        compiled_file["fragment_path"] = PurePosixPath(*relative_parts).as_posix()
        files.append(compiled_file)
    payload["files"] = files
    if compute_generation(payload) != generation:
        raise ValueError("manifest generation does not match its descriptor")
    return manifest


def publish_generation(
    output_root: Path,
    manifest: CompiledProfileManifest,
    fragment_payloads: Mapping[PurePosixPath | str, bytes],
) -> Path:
    """Publish a verified generation and its manifest without partial state."""
    output_root = Path(output_root)
    manifest_path = output_root / "manifest.json"
    _validate_manifest_control(manifest_path)
    expected = _expected_fragments(manifest, fragment_payloads)
    manifest_payload = encode_manifest(manifest)
    expected[PurePosixPath("manifest.json")] = (manifest_payload, 0o600)

    _ensure_control_directory(output_root, kind="output root")
    generations_root = output_root / _GENERATIONS
    _ensure_control_directory(generations_root, kind="generation root")

    generation_root = generations_root / manifest.generation
    _cleanup_staging(generations_root, manifest.generation)
    if generation_root.is_symlink():
        raise ValueError(f"generation path is a symlink: {generation_root}")
    if generation_root.exists():
        if not generation_root.is_dir():
            raise ValueError(f"generation path is not a directory: {generation_root}")
        _verify_existing_generation(generation_root, expected)
    else:
        _write_new_generation(generations_root, generation_root, expected)

    _replace_manifest(manifest_path, manifest_payload)
    return manifest_path


def _expected_fragments(
    manifest: CompiledProfileManifest,
    fragment_payloads: Mapping[PurePosixPath | str, bytes],
) -> dict[PurePosixPath, tuple[bytes, int]]:
    payloads = {PurePosixPath(fragment): payload for fragment, payload in fragment_payloads.items()}
    prefix = _GENERATIONS / manifest.generation
    expected: dict[PurePosixPath, tuple[bytes, int]] = {}
    for compiled_file in manifest.files:
        fragment = PurePosixPath(compiled_file.fragment_path)
        if fragment.parts[: len(prefix.parts)] != prefix.parts:
            raise ValueError(
                f"fragment path {fragment} must start with generations/{manifest.generation}/"
            )
        relative_parts = fragment.parts[len(prefix.parts) :]
        if not relative_parts:
            raise ValueError(f"fragment path {fragment} has no generation-relative suffix")
        relative = PurePosixPath(*relative_parts)
        if relative.parts[:1] == ("manifest.json",):
            raise ValueError(f"fragment path conflicts with generation manifest: {fragment}")
        if relative in expected:
            raise ValueError(f"duplicate compiled fragment: {fragment}")
        try:
            payload = payloads[relative]
        except KeyError as exc:
            raise ValueError(f"missing payload for compiled fragment: {relative}") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if digest != compiled_file.sha256:
            raise ValueError(f"payload digest mismatch for compiled fragment: {relative}")
        expected[relative] = (payload, compiled_file.mode)
    return expected


def _verify_existing_generation(
    generation_root: Path,
    expected: Mapping[PurePosixPath, tuple[bytes, int]],
) -> None:
    actual: dict[PurePosixPath, tuple[bytes, int]] = {}
    for path in sorted(generation_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"generation contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"generation contains a non-file path: {path}")
        relative = PurePosixPath(*path.relative_to(generation_root).parts)
        actual[relative] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))

    if set(actual) != set(expected):
        raise ValueError(f"generation {generation_root.name} has unexpected fragments")
    for relative, (payload, mode) in expected.items():
        if actual[relative] != (payload, mode):
            raise FileExistsError(f"generation {generation_root.name} has different bytes or modes")


def _write_new_generation(
    generations_root: Path,
    generation_root: Path,
    expected: Mapping[PurePosixPath, tuple[bytes, int]],
) -> None:
    staging = Path(tempfile.mkdtemp(prefix=f".{generation_root.name}.", dir=generations_root))
    try:
        for relative, (payload, mode) in sorted(
            expected.items(), key=lambda item: item[0].as_posix()
        ):
            destination = staging.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        _fsync_directory(staging)
        os.replace(staging, generation_root)
        staging = None
        _fsync_directory(generations_root)
    finally:
        if staging is not None:
            active_exception = sys.exc_info()[1]
            try:
                shutil.rmtree(staging)
            except BaseException as cleanup_error:
                if active_exception is None:
                    raise
                active_exception.add_note(
                    f"could not clean generation staging {staging}: {cleanup_error}"
                )


def _cleanup_staging(generations_root: Path, generation: str) -> None:
    prefix = f".{generation}."
    for candidate in generations_root.iterdir():
        if not candidate.name.startswith(prefix):
            continue
        if candidate.is_symlink():
            raise ValueError(f"generation staging path is a symlink: {candidate}")
        if candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()


def _ensure_control_directory(path: Path, *, kind: str) -> None:
    _reject_symlink_components(path, kind=kind)
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir(parents=True, exist_ok=True)
        return
    except OSError as exc:
        raise ValueError(f"could not inspect {kind}: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{kind} is a symlink: {path}")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"{kind} is not a directory: {path}")


def _reject_symlink_components(path: Path, *, kind: str) -> None:
    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ValueError(f"could not inspect {kind}: {current}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"{kind} contains a symlink boundary: {current}")


def _validate_manifest_control(path: Path) -> None:
    _reject_symlink_components(path, kind="manifest path")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError(f"could not inspect manifest path: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"manifest path is not a regular file: {path}")


def _replace_manifest(path: Path, payload: bytes) -> None:
    _validate_manifest_control(path)
    fd, temporary_name = tempfile.mkstemp(prefix=".manifest.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_manifest_control(path)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        active_exception = sys.exc_info()[1]
        try:
            temporary.unlink(missing_ok=True)
        except BaseException as cleanup_error:
            if active_exception is None:
                raise
            active_exception.add_note(
                f"could not clean temporary manifest {temporary}: {cleanup_error}"
            )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "bind_generation",
    "compute_generation",
    "generation_descriptor",
    "publish_generation",
    "validate_generation_binding",
]
