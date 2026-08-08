"""Behavioral tests for canonical profile-manifest generations."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
from pathlib import Path

import cheese_flow.profiles.generation as generation_module
import pytest
from cheese_flow.profiles.generation import (
    bind_generation,
    compute_generation,
    generation_descriptor,
    publish_generation,
    validate_generation_binding,
)
from cheese_flow.profiles.manifest_codec import (
    canonical_json_bytes,
    decode_manifest,
    encode_manifest,
    load_manifest,
)
from cheese_flow.profiles.models import CompiledFile, CompileTarget


def _target() -> CompileTarget:
    return CompileTarget(
        name="home",
        symbolic_root="$HOME",
        resolved_root=Path("/home/tester"),
        harnesses=("claude",),
    )


def _descriptor(
    *,
    payload: bytes = b'{"enabled":true}\n',
    mode: int = 0o600,
) -> tuple[dict[str, object], bytes]:
    fragment_hash = hashlib.sha256(payload).hexdigest()
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=(_target(),),
        files=(
            CompiledFile(
                target="home",
                harness="claude",
                fragment_path="home/claude/settings.json",
                destination_path=".claude/settings.json",
                sha256=fragment_hash,
                mode=mode,
            ),
        ),
        drift=(),
    )
    return descriptor, payload


def test_canonical_json_is_stable_and_compact() -> None:
    assert canonical_json_bytes({"z": 2, "a": [True, "é"]}) == ('{"a":[true,"é"],"z":2}'.encode())


def test_generation_binds_relative_paths_without_a_self_reference() -> None:
    descriptor, _ = _descriptor()
    expected = hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()

    manifest = bind_generation(descriptor)

    assert manifest.generation == expected
    assert manifest.files[0].fragment_path.as_posix() == (
        f"generations/{expected}/home/claude/settings.json"
    )
    assert validate_generation_binding(manifest) == manifest
    assert "generation" not in descriptor


def test_file_order_is_part_of_the_generation_digest() -> None:
    descriptor, _ = _descriptor()
    first = descriptor["files"][0]
    second = {
        **first,
        "destination_path": "/home/tester/.claude/other.json",
        "fragment_path": "home/claude/other.json",
    }
    ordered_descriptor = {**descriptor, "files": [first, second]}
    reversed_descriptor = {**descriptor, "files": [second, first]}

    assert compute_generation(ordered_descriptor) != compute_generation(reversed_descriptor)
    with pytest.raises(ValueError, match="must not contain generation"):
        compute_generation({**descriptor, "generation": "0" * 64})


def test_manifest_codec_round_trips_canonical_bytes() -> None:
    descriptor, _ = _descriptor()
    manifest = bind_generation(descriptor)

    encoded = encode_manifest(manifest)
    decoded = decode_manifest(encoded)

    assert decoded == manifest
    assert encoded == encode_manifest(decoded)


def test_publish_writes_immutable_generation_then_replaces_root_manifest(tmp_path: Path) -> None:
    descriptor, payload = _descriptor()
    manifest = bind_generation(descriptor)
    output_root = tmp_path / "compiled"

    manifest_path = publish_generation(
        output_root,
        manifest,
        {"home/claude/settings.json": payload},
    )

    assert manifest_path == output_root / "manifest.json"
    assert (
        output_root / "generations" / manifest.generation / "home/claude/settings.json"
    ).read_bytes() == payload
    assert load_manifest(manifest_path) == manifest
    generation_manifest = output_root / "generations" / manifest.generation / "manifest.json"
    assert generation_manifest.read_bytes() == encode_manifest(manifest)
    assert manifest_path.read_bytes() == generation_manifest.read_bytes()

    first_manifest_bytes = manifest_path.read_bytes()
    publish_generation(output_root, manifest, {"home/claude/settings.json": payload})
    assert manifest_path.read_bytes() == first_manifest_bytes

    generation_manifest.write_bytes(b"tampered")
    with pytest.raises(FileExistsError, match="different bytes"):
        publish_generation(output_root, manifest, {"home/claude/settings.json": payload})
    generation_manifest.write_bytes(encode_manifest(manifest))

    generation_file = (
        output_root / "generations" / manifest.generation / "home/claude/settings.json"
    )
    generation_file.write_bytes(b"tampered")
    with pytest.raises(FileExistsError, match="different bytes"):
        publish_generation(output_root, manifest, {"home/claude/settings.json": payload})
    assert json.loads(manifest_path.read_text()) == json.loads(encode_manifest(manifest))


def test_mode_changes_generation_identity_and_published_file_mode(tmp_path: Path) -> None:
    default_descriptor, payload = _descriptor()
    executable_descriptor, _ = _descriptor(mode=0o755)
    default_manifest = bind_generation(default_descriptor)
    executable_manifest = bind_generation(executable_descriptor)

    assert executable_manifest.generation != default_manifest.generation
    publish_generation(
        tmp_path / "compiled",
        executable_manifest,
        {"home/claude/settings.json": payload},
    )
    destination = (
        tmp_path
        / "compiled"
        / "generations"
        / executable_manifest.generation
        / "home"
        / "claude"
        / "settings.json"
    )
    assert stat.S_IMODE(destination.stat().st_mode) == 0o755


def test_publish_rejects_symlinked_generation_control_directory(tmp_path: Path) -> None:
    descriptor, payload = _descriptor()
    manifest = bind_generation(descriptor)
    output_root = tmp_path / "compiled"
    output_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output_root / "generations").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        publish_generation(output_root, manifest, {"home/claude/settings.json": payload})

    assert tuple(outside.iterdir()) == ()


@pytest.mark.parametrize("special", ("fifo", "socket"))
def test_publish_rejects_special_root_manifest_before_staging(tmp_path: Path, special: str) -> None:
    descriptor, payload = _descriptor()
    manifest = bind_generation(descriptor)
    output_root = tmp_path / "compiled"
    output_root.mkdir()
    manifest_path = output_root / "manifest.json"
    listener: socket.socket | None = None
    if special == "fifo":
        os.mkfifo(manifest_path)
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(manifest_path))

    try:
        with pytest.raises(ValueError, match="regular file"):
            publish_generation(output_root, manifest, {"home/claude/settings.json": payload})
        assert manifest_path.exists()
        assert not (output_root / "generations").exists()
    finally:
        if listener is not None:
            listener.close()
        manifest_path.unlink(missing_ok=True)


def test_publish_rejects_manifest_prefix_fragment_before_staging(tmp_path: Path) -> None:
    descriptor, payload = _descriptor()
    descriptor["files"] = [
        {
            **descriptor["files"][0],
            "fragment_path": "manifest.json/child",
        }
    ]
    manifest = bind_generation(descriptor)

    with pytest.raises(ValueError, match="conflicts with generation manifest"):
        publish_generation(
            tmp_path / "compiled",
            manifest,
            {"manifest.json/child": payload},
        )

    assert not (tmp_path / "compiled").exists()


def test_interrupted_generation_publication_cleans_staging_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor, payload = _descriptor()
    manifest = bind_generation(descriptor)
    output_root = tmp_path / "compiled"
    original_replace = generation_module.os.replace

    def fail_generation_replace(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == output_root / "generations" / manifest.generation:
            raise OSError("interrupted publication")
        original_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(generation_module.os, "replace", fail_generation_replace)
        with pytest.raises(OSError, match="interrupted publication"):
            publish_generation(output_root, manifest, {"home/claude/settings.json": payload})

    generations_root = output_root / "generations"
    assert (
        tuple(
            path
            for path in generations_root.iterdir()
            if path.name.startswith(f".{manifest.generation}.")
        )
        == ()
    )
    publish_generation(output_root, manifest, {"home/claude/settings.json": payload})
