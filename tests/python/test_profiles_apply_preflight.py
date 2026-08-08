"""Behavioral tests for complete, mutation-free profile apply preflight."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
from pathlib import Path, PurePosixPath

import cheese_flow.profiles.compile as compile_module
import pytest
from cheese_flow.profiles.apply import apply_profile
from cheese_flow.profiles.errors import ProfileApplyError
from cheese_flow.profiles.generation import (
    bind_generation,
    generation_descriptor,
    publish_generation,
)
from cheese_flow.profiles.models import (
    CompiledFile,
    CompiledProfileManifest,
    CompileRequest,
    CompileTarget,
    DriftRecord,
    ProfileApplyState,
)
from cheese_flow.profiles.preflight import preflight_apply, revalidate_parent_chain


def _published(
    tmp_path: Path,
    files: tuple[tuple[str, str, str, bytes], ...] = (("home", "claude", "z.json", b"z-content"),),
    *,
    resolved_root: Path | None = None,
    drift: tuple[DriftRecord, ...] = (),
) -> tuple[Path, Path, Path, CompiledProfileManifest]:
    target_root = tmp_path / "target" if resolved_root is None else resolved_root
    if not target_root.exists():
        target_root.mkdir(parents=True)
    output_root = tmp_path / "compiled"
    target = CompileTarget(
        name="home",
        symbolic_root="$HOME",
        resolved_root=target_root,
        harnesses=("claude",),
    )
    compiled_files = tuple(
        CompiledFile(
            target=target_name,
            harness=harness,
            fragment_path=f"{target_name}/{harness}/fragments/{index}",
            destination_path=name,
            sha256=hashlib.sha256(content).hexdigest(),
        )
        for index, (target_name, harness, name, content) in enumerate(files)
    )
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=(target,),
        files=compiled_files,
        drift=drift,
    )
    manifest = bind_generation(descriptor)
    payloads = {
        f"{target_name}/{harness}/fragments/{index}": content
        for index, (target_name, harness, name, content) in enumerate(files)
    }
    manifest_path = publish_generation(output_root, manifest, payloads)
    return manifest_path, target_root, output_root, manifest


def test_preflight_binds_generation_loads_bytes_and_sorts_ownership(tmp_path: Path) -> None:
    manifest_path, target_root, _, manifest = _published(
        tmp_path,
        files=(
            ("home", "claude", "z.json", b"z-content"),
            ("home", "claude", "a.json", b"a-content"),
        ),
    )
    prior_path = target_root / "stale.json"
    prior_path.write_bytes(b"old")
    previous = ProfileApplyState(schema_version=1, managed_files=(prior_path,))

    plan = preflight_apply(manifest_path, previous)

    assert plan.generation == manifest.generation
    assert plan.managed_files == (target_root / "a.json", target_root / "z.json")
    assert plan.target_roots == (target_root,)
    assert plan.stale_files == (prior_path,)
    assert tuple(item.destination for item in plan.replacements) == plan.managed_files
    assert plan.replacements[0].content == b"a-content"
    assert plan.replacements[0].sha256 == hashlib.sha256(b"a-content").hexdigest()
    assert "a-content" not in repr(plan.replacements[0])


def test_apply_accepts_multiple_leaf_drift_records_for_one_destination(
    tmp_path: Path,
) -> None:
    drift = (
        DriftRecord(
            target="home",
            destination_path="profile.json",
            path="enabled",
            baseline=False,
            live=True,
            compiled=False,
        ),
        DriftRecord(
            target="home",
            destination_path="profile.json",
            path="nested.mode",
            baseline=1,
            live=2,
            compiled=3,
        ),
    )
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        files=(("home", "claude", "profile.json", b"compiled"),),
        drift=drift,
    )

    report = apply_profile(manifest_path, state_path=tmp_path / "state" / "apply-state.json")

    assert report.copied == (target_root / "profile.json",)
    assert (target_root / "profile.json").read_bytes() == b"compiled"


def test_preflight_rejects_duplicate_leaf_drift_record(tmp_path: Path) -> None:
    drift = (
        DriftRecord(
            target="home",
            destination_path="profile.json",
            path="enabled",
            baseline=False,
            live=True,
            compiled=False,
        ),
    ) * 2
    manifest_path, target_root, _, _ = _published(tmp_path, files=(), drift=drift)

    with pytest.raises(ProfileApplyError, match="duplicate drift record"):
        preflight_apply(manifest_path, None)

    assert tuple(target_root.iterdir()) == ()


def test_preflight_stale_only_plan_keeps_target_root_provenance(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path, files=())
    stale_path = target_root / "removed.json"
    stale_path.write_bytes(b"old")
    previous = ProfileApplyState(schema_version=1, managed_files=(stale_path,))

    plan = preflight_apply(manifest_path, previous)

    assert plan.replacements == ()
    assert plan.target_roots == (target_root,)
    assert plan.stale_files == (stale_path,)
    assert plan.managed_files == ()


def test_preflight_rejects_tampered_fragment_before_live_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, manifest = _published(tmp_path)
    fragment = manifest_path.parent / manifest.files[0].fragment_path
    fragment.write_bytes(b"tampered")

    with pytest.raises(ProfileApplyError, match="hash mismatch"):
        preflight_apply(manifest_path, None)

    assert tuple(target_root.iterdir()) == ()


def test_preflight_rejects_unknown_target_and_harness(tmp_path: Path) -> None:
    manifest_path, _, output_root, _ = _published(tmp_path)
    target_root = tmp_path / "target"
    target = CompileTarget(
        name="home",
        symbolic_root="$HOME",
        resolved_root=target_root,
        harnesses=("claude",),
    )
    payload = b"content"
    unknown_target = CompiledFile(
        target="other",
        harness="claude",
        fragment_path="other/claude/file.json",
        destination_path="other.json",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=(target,),
        files=(unknown_target,),
        drift=(),
    )
    unknown_manifest = bind_generation(descriptor)
    unknown_path = publish_generation(
        output_root / "unknown",
        unknown_manifest,
        {"other/claude/file.json": payload},
    )

    with pytest.raises(ProfileApplyError, match="unknown target"):
        preflight_apply(unknown_path, None)

    unknown_harness = unknown_target.model_copy(update={"target": "home", "harness": "codex"})
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=(target,),
        files=(unknown_harness,),
        drift=(),
    )
    harness_manifest = bind_generation(descriptor)
    harness_path = publish_generation(
        output_root / "harness", harness_manifest, {"other/claude/file.json": payload}
    )

    with pytest.raises(ProfileApplyError, match="not owned"):
        preflight_apply(harness_path, None)


def test_preflight_rejects_duplicate_destinations(tmp_path: Path) -> None:
    manifest_path, _, output_root, _ = _published(tmp_path)
    target_root = tmp_path / "target"
    target = CompileTarget(
        name="home",
        symbolic_root="$HOME",
        resolved_root=target_root,
        harnesses=("claude",),
    )
    files = (
        CompiledFile(
            target="home",
            harness="claude",
            fragment_path="home/claude/first.json",
            destination_path="same.json",
            sha256=hashlib.sha256(b"first").hexdigest(),
        ),
        CompiledFile(
            target="home",
            harness="claude",
            fragment_path="home/claude/second.json",
            destination_path="same.json",
            sha256=hashlib.sha256(b"second").hexdigest(),
        ),
    )
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=(target,),
        files=files,
        drift=(),
    )
    manifest = bind_generation(descriptor)
    duplicate_path = publish_generation(
        output_root / "duplicate",
        manifest,
        {"home/claude/first.json": b"first", "home/claude/second.json": b"second"},
    )

    with pytest.raises(ProfileApplyError, match="duplicate destination"):
        preflight_apply(duplicate_path, None)
    assert tuple(target_root.iterdir()) == ()
    assert manifest_path.exists()


def test_preflight_rejects_fragment_symlink_and_prior_escape(tmp_path: Path) -> None:
    manifest_path, target_root, _, manifest = _published(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    fragment = manifest_path.parent / manifest.files[0].fragment_path
    fragment.unlink()
    fragment.symlink_to(outside)

    with pytest.raises(ProfileApplyError, match="symlink"):
        preflight_apply(manifest_path, None)
    assert tuple(target_root.iterdir()) == ()

    prior_dir = tmp_path / "prior"
    prior_dir.mkdir()
    prior_manifest, prior_target_root, _, _ = _published(prior_dir)
    prior_outside = tmp_path / "prior-outside"
    prior_outside.write_bytes(b"outside")
    with pytest.raises(ProfileApplyError, match="outside"):
        preflight_apply(
            prior_manifest,
            ProfileApplyState(schema_version=1, managed_files=(prior_outside,)),
        )
    assert tuple(prior_target_root.iterdir()) == ()


def test_revalidate_parent_chain_rejects_symlink_boundary(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    destination = target_root / "nested" / "profile.json"

    revalidate_parent_chain(destination, target_root)

    outside = tmp_path / "outside"
    outside.mkdir()
    (target_root / "nested").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProfileApplyError, match="symlink"):
        revalidate_parent_chain(destination, target_root)


def test_revalidate_rejects_replaced_root_symlink(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    destination = target_root / "file.json"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_root = tmp_path / "real-target"
    target_root.rename(real_root)
    target_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProfileApplyError, match="symlink"):
        revalidate_parent_chain(destination, target_root)


def test_preflight_rejects_tampered_manifest_before_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path)
    payload = json.loads(manifest_path.read_text())
    payload["files"][0]["fragment_path"] = "generations/other/file.json"
    manifest_path.write_text(json.dumps(payload))

    with pytest.raises(ProfileApplyError, match="generation binding"):
        preflight_apply(manifest_path, None)
    assert tuple(target_root.iterdir()) == ()


def test_preflight_rejects_compile_root_symlink_before_target_mutation(tmp_path: Path) -> None:
    real_root = tmp_path / "real-target"
    real_root.mkdir()
    lexical_root = tmp_path / "target-link"
    lexical_root.symlink_to(real_root, target_is_directory=True)
    manifest_path, _, _, _ = _published(tmp_path, resolved_root=lexical_root)

    with pytest.raises(ProfileApplyError, match="symlink|canonical"):
        preflight_apply(manifest_path, None)

    assert tuple(real_root.iterdir()) == ()


def test_preflight_rejects_final_symlink_in_prior_state(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"must-survive")
    managed = target_root / "managed.json"
    managed.symlink_to(outside)
    prior = ProfileApplyState(schema_version=1, managed_files=(managed,))

    with pytest.raises(ProfileApplyError, match="symlink"):
        preflight_apply(manifest_path, prior)

    assert outside.read_bytes() == b"must-survive"


def test_preflight_rejects_desired_ancestor_descendant_destinations(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        files=(
            ("home", "claude", "a", b"ancestor"),
            ("home", "claude", "a/b", b"descendant"),
        ),
    )

    with pytest.raises(ProfileApplyError, match="ancestor/descendant"):
        preflight_apply(manifest_path, None)

    assert tuple(target_root.iterdir()) == ()


@pytest.mark.parametrize("prior_name,desired_name", [("a", "a/b"), ("a/b", "a")])
def test_preflight_rejects_structural_stale_desired_conflicts(
    tmp_path: Path,
    prior_name: str,
    desired_name: str,
) -> None:
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        files=(("home", "claude", desired_name, b"desired"),),
    )
    prior = ProfileApplyState(
        schema_version=1,
        managed_files=(target_root / prior_name,),
    )

    with pytest.raises(ProfileApplyError, match="ancestor/descendant"):
        preflight_apply(manifest_path, prior)

    assert tuple(target_root.iterdir()) == ()


def test_preflight_rejects_manifest_control_alias(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        resolved_root=tmp_path / "compiled",
        files=(("home", "claude", "manifest.json", b"target"),),
    )

    with pytest.raises(ProfileApplyError, match="reserved control path"):
        preflight_apply(manifest_path, None)

    assert manifest_path.exists()


def test_preflight_rejects_control_control_alias_before_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path)
    aliased = tmp_path / "state" / "apply-state.journal"

    with pytest.raises(ProfileApplyError, match="control paths conflict"):
        preflight_apply(
            manifest_path,
            None,
            reserved_paths={"state": aliased, "journal": aliased},
        )

    assert tuple(target_root.iterdir()) == ()


def test_preflight_rejects_stale_control_alias_before_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path)
    state_path = target_root / "apply-state.json"
    journal_path = Path(f"{state_path}.journal")
    prior = ProfileApplyState(schema_version=1, managed_files=(journal_path,))

    with pytest.raises(ProfileApplyError, match="reserved control path"):
        preflight_apply(
            manifest_path,
            prior,
            reserved_paths={
                "state": state_path,
                "journal": journal_path,
                "lock": Path(f"{state_path}.lock"),
            },
        )

    assert tuple(target_root.iterdir()) == ()


def test_preflight_rejects_temporary_control_alias_before_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        files=(("home", "claude", ".apply-state.json.synthetic.tmp", b"target"),),
    )
    state_path = target_root / "apply-state.json"

    with pytest.raises(ProfileApplyError, match="reserved control path"):
        preflight_apply(manifest_path, None, reserved_paths={"state": state_path})

    assert tuple(target_root.iterdir()) == ()


@pytest.mark.parametrize("special", ("fifo", "socket"))
def test_apply_rejects_special_existing_destinations_before_journal(
    tmp_path: Path, special: str
) -> None:
    manifest_path, target_root, _, _ = _published(
        tmp_path,
        files=(("home", "claude", "z.json", b"target"),),
    )
    destination = target_root / "z.json"
    listener: socket.socket | None = None
    if special == "fifo":
        os.mkfifo(destination)
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(destination))

    state_path = tmp_path / "state" / "apply-state.json"
    journal_path = Path(f"{state_path}.journal")
    try:
        with pytest.raises(ProfileApplyError, match="not a regular file"):
            apply_profile(manifest_path, state_path=state_path)
        assert destination.exists()
        assert not journal_path.exists()
    finally:
        if listener is not None:
            listener.close()
        destination.unlink(missing_ok=True)


@pytest.mark.parametrize("special", ("fifo", "socket"))
def test_apply_rejects_special_existing_lock_before_open(tmp_path: Path, special: str) -> None:
    manifest_path, target_root, _, _ = _published(tmp_path)
    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    lock_path = Path(f"{state_path}.lock")
    listener: socket.socket | None = None
    if special == "fifo":
        os.mkfifo(lock_path)
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(lock_path))

    try:
        with pytest.raises(ProfileApplyError, match="not a regular file"):
            apply_profile(manifest_path, state_path=state_path)
        assert lock_path.exists()
        assert tuple(target_root.iterdir()) == ()
        assert not Path(f"{state_path}.journal").exists()
    finally:
        if listener is not None:
            listener.close()
        lock_path.unlink(missing_ok=True)


def test_public_apply_works_after_source_and_baseline_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "live"
    profile_dir.mkdir(parents=True)
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    target_root = tmp_path / "target"
    target_root.mkdir()
    output_root = tmp_path / "compiled"
    (profile_dir / "profile.yaml").write_text(
        "name: live\ncompile_targets:\n  home:\n    target_root: $HOME\n    harnesses: [claude]\n",
        encoding="utf-8",
    )

    class _Renderer:
        def render(self, profile, target: Path, *, logical_root: Path):
            del profile, logical_root
            destination = target / ".generated" / "profile.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'{"compiled":true}\n')
            return (PurePosixPath(".generated/profile.json"),)

    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())
    manifest = compile_module.compile_profile(
        CompileRequest(
            profile_name="live",
            source_root=source_root,
            baseline_root=baseline_root,
            output_root=output_root,
        ),
        environment={"HOME": str(target_root)},
    )
    manifest_path = output_root / "manifest.json"
    assert manifest.generation

    shutil.rmtree(source_root)
    shutil.rmtree(baseline_root)
    assert not source_root.exists()
    assert not baseline_root.exists()
    state_path = tmp_path / "state" / "apply-state.json"

    report = apply_profile(manifest_path, state_path=state_path)

    destination = target_root / ".generated" / "profile.json"
    assert report.copied == (destination,)
    assert destination.read_bytes() == b'{"compiled":true}\n'
    assert state_path.is_file()
    assert not Path(f"{state_path}.journal").exists()


def test_public_apply_rejects_a_later_invalid_fragment_before_mutation(tmp_path: Path) -> None:
    manifest_path, target_root, _, manifest = _published(
        tmp_path,
        files=(
            ("home", "claude", "first.json", b"first"),
            ("home", "claude", "second.json", b"second"),
        ),
    )
    second_fragment = manifest_path.parent / manifest.files[1].fragment_path
    second_fragment.write_bytes(b"tampered")
    first_destination = target_root / "first.json"
    first_destination.write_bytes(b"existing")
    stale_destination = target_root / "stale.json"
    stale_destination.write_bytes(b"stale")
    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    state_payload = {
        "schema_version": 1,
        "managed_files": [str(first_destination), str(stale_destination)],
    }
    state_path.write_text(json.dumps(state_payload, separators=(",", ":")) + "\n", encoding="utf-8")
    lock_path = Path(f"{state_path}.lock")
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    lock_mode = lock_path.stat().st_mode
    state_bytes = state_path.read_bytes()
    lock_bytes = lock_path.read_bytes()
    journal_path = Path(f"{state_path}.journal")

    with pytest.raises(ProfileApplyError, match="hash mismatch"):
        apply_profile(manifest_path, state_path=state_path)

    assert first_destination.read_bytes() == b"existing"
    assert stale_destination.read_bytes() == b"stale"
    assert not (target_root / "second.json").exists()
    assert state_path.read_bytes() == state_bytes
    assert lock_path.read_bytes() == lock_bytes
    assert lock_path.stat().st_mode == lock_mode
    assert not journal_path.exists()
