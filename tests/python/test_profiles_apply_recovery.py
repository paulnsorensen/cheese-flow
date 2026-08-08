"""Behavioral tests for journaled profile apply recovery and legacy migration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cheese_flow.profiles.apply as apply_module
import pytest
from cheese_flow.profiles.apply import _control_paths, apply_profile
from cheese_flow.profiles.errors import ProfileApplyError
from cheese_flow.profiles.generation import (
    bind_generation,
    generation_descriptor,
    publish_generation,
)
from cheese_flow.profiles.journal import load_journal, prepare_journal
from cheese_flow.profiles.models import CompiledFile, CompileTarget


def _publish(
    output_root: Path,
    targets: tuple[tuple[str, Path, str], ...],
    files: tuple[tuple[str, str, str, bytes], ...],
) -> tuple[Path, object]:
    compile_targets = tuple(
        CompileTarget(
            name=name,
            symbolic_root=f"${name.upper()}",
            resolved_root=root,
            harnesses=(harness,),
        )
        for name, root, harness in targets
    )
    compiled_files = tuple(
        CompiledFile(
            target=target,
            harness=harness,
            fragment_path=f"{target}/{harness}/fragments/{index}",
            destination_path=destination,
            sha256=hashlib.sha256(content).hexdigest(),
        )
        for index, (target, harness, destination, content) in enumerate(files)
    )
    descriptor = generation_descriptor(
        schema_version=1,
        profile="live",
        source_id="profiles/live",
        compile_targets=compile_targets,
        files=compiled_files,
        drift=(),
    )
    manifest = bind_generation(descriptor)
    payloads = {
        f"{target}/{harness}/fragments/{index}": content
        for index, (target, harness, destination, content) in enumerate(files)
    }
    return publish_generation(output_root, manifest, payloads), manifest


def test_pending_journal_finishes_before_a_different_manifest_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    output_root = tmp_path / "compiled"
    old_manifest_path, old_manifest = _publish(
        output_root,
        (("home", target_root, "claude"),),
        (("home", "claude", "profile.json", b"old"),),
    )
    state_path = tmp_path / "state" / "apply-state.json"
    journal_path = Path(f"{state_path}.journal")
    write_real = apply_module.write_replacements
    attempted: list[str] = []

    def crash_after_write(plan):
        attempted.append(plan.generation)
        write_real(plan)
        raise ProfileApplyError("simulated crash")

    with monkeypatch.context() as patch:
        patch.setattr(apply_module, "write_replacements", crash_after_write)
        with pytest.raises(ProfileApplyError, match="simulated crash"):
            apply_profile(old_manifest_path, state_path=state_path)

    journal = load_journal(journal_path)
    old_snapshot = output_root / "generations" / old_manifest.generation / "manifest.json"
    assert journal.manifest_path == old_snapshot
    assert journal.manifest_sha256 == hashlib.sha256(old_snapshot.read_bytes()).hexdigest()
    assert attempted == [old_manifest.generation]

    new_manifest_path, new_manifest = _publish(
        output_root,
        (("home", target_root, "claude"),),
        (("home", "claude", "profile.json", b"new"),),
    )
    recovered: list[str] = []

    def record_write(plan):
        recovered.append(plan.generation)
        return write_real(plan)

    monkeypatch.setattr(apply_module, "write_replacements", record_write)
    report = apply_profile(new_manifest_path, state_path=state_path)

    assert recovered == [old_manifest.generation, new_manifest.generation]
    assert (target_root / "profile.json").read_bytes() == b"new"
    assert report.state.managed_files == (target_root / "profile.json",)
    assert not journal_path.exists()


def test_state_filename_controls_are_injective(tmp_path: Path) -> None:
    json_state = tmp_path / "state" / "apply-state.json"
    yaml_state = tmp_path / "state" / "apply-state.yaml"

    json_controls = _control_paths(json_state)
    yaml_controls = _control_paths(yaml_state)

    assert json_controls["journal"] == Path(f"{json_state}.journal")
    assert yaml_controls["journal"] == Path(f"{yaml_state}.journal")
    assert json_controls["lock"] == Path(f"{json_state}.lock")
    assert yaml_controls["lock"] == Path(f"{yaml_state}.lock")
    assert json_controls["journal"] != yaml_controls["journal"]
    assert json_controls["lock"] != yaml_controls["lock"]


def test_legacy_root_pointer_journal_recovers_unchanged(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, manifest = _publish(
        tmp_path / "compiled",
        (("home", target_root, "claude"),),
        (("home", "claude", "profile.json", b"legacy"),),
    )
    state_path = tmp_path / "state" / "apply-state.json"
    journal_path = Path(f"{state_path}.journal")
    desired = (target_root / "profile.json",)
    prepare_journal(
        journal_path,
        generation=manifest.generation,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        previous_managed=(),
        desired_managed=desired,
    )

    report = apply_profile(manifest_path, state_path=state_path)

    assert (target_root / "profile.json").read_bytes() == b"legacy"
    assert report.state.managed_files == desired
    assert not journal_path.exists()


def test_exact_legacy_state_migrates_after_successful_apply_with_nested_roots(
    tmp_path: Path,
) -> None:
    outer_root = tmp_path / "target"
    nested_root = outer_root / "nested"
    nested_root.mkdir(parents=True)
    manifest_path, _ = _publish(
        tmp_path / "compiled",
        (("outer", outer_root, "claude"), ("nested", nested_root, "codex")),
        (
            ("outer", "claude", "outer.json", b"outer"),
            ("nested", "codex", "nested.json", b"nested"),
        ),
    )
    stale = nested_root / "stale.json"
    stale.write_bytes(b"stale")
    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps({"managed_files": [str(stale)]}) + "\n", encoding="utf-8")

    report = apply_profile(manifest_path, state_path=state_path)

    desired = tuple(sorted((outer_root / "outer.json", nested_root / "nested.json")))
    assert report.copied == desired
    assert report.deleted == (stale,)
    assert not stale.exists()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "managed_files": [str(path) for path in desired],
    }


@pytest.mark.parametrize(
    "state_payload",
    [
        {"managed_files": [], "unexpected": True},
        {"managed_files": ["/outside/profile.json"]},
    ],
)
def test_unexpected_legacy_state_fails_without_target_mutation(
    tmp_path: Path, state_payload: dict[str, object]
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, _ = _publish(
        tmp_path / "compiled",
        (("home", target_root, "claude"),),
        (("home", "claude", "profile.json", b"new"),),
    )
    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    original = json.dumps(state_payload, sort_keys=True) + "\n"
    state_path.write_text(original, encoding="utf-8")

    with pytest.raises(ProfileApplyError):
        apply_profile(manifest_path, state_path=state_path)

    assert not (target_root / "profile.json").exists()
    assert state_path.read_text(encoding="utf-8") == original


def test_legacy_state_is_not_migrated_when_journaled_apply_does_not_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, _ = _publish(
        tmp_path / "compiled",
        (("home", target_root, "claude"),),
        (("home", "claude", "profile.json", b"new"),),
    )
    stale = target_root / "stale.json"
    stale.write_bytes(b"stale")
    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    original = json.dumps({"managed_files": [str(stale)]}) + "\n"
    state_path.write_text(original, encoding="utf-8")

    def fail_delete(_plan):
        raise ProfileApplyError("stop before journal completion")

    monkeypatch.setattr(apply_module, "delete_stale", fail_delete)

    with pytest.raises(ProfileApplyError, match="stop before journal completion"):
        apply_profile(manifest_path, state_path=state_path)

    assert state_path.read_text(encoding="utf-8") == original
    Path(f"{state_path}.journal")


def test_state_symlink_laundering_cannot_delete_unlisted_target(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, _ = _publish(
        tmp_path / "compiled",
        (("home", target_root, "claude"),),
        (("home", "claude", "new.json", b"new"),),
    )
    other_root = target_root / "other"
    other_root.mkdir()
    unlisted = other_root / "secret.json"
    unlisted.write_bytes(b"must-survive")
    managed_link = target_root / "managed"
    managed_link.mkdir()
    lexical_managed = managed_link / "secret.json"
    managed_link.rmdir()
    managed_link.symlink_to(other_root, target_is_directory=True)

    state_path = tmp_path / "state" / "apply-state.json"
    state_path.parent.mkdir()
    original = json.dumps({"managed_files": [str(lexical_managed)]}) + "\n"
    state_path.write_text(original, encoding="utf-8")
    journal_path = Path(f"{state_path}.journal")

    with pytest.raises(ProfileApplyError, match="symlink"):
        apply_profile(manifest_path, state_path=state_path)

    assert unlisted.read_bytes() == b"must-survive"
    assert not (target_root / "new.json").exists()
    assert not journal_path.exists()
    assert state_path.read_text(encoding="utf-8") == original


def test_recovery_rejects_prefix_conflict_before_target_or_journal_mutation(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, manifest = _publish(
        tmp_path / "compiled-prefix",
        (("home", target_root, "claude"),),
        (
            ("home", "claude", "a", b"ancestor"),
            ("home", "claude", "a/b", b"descendant"),
        ),
    )
    replacement_manifest, _ = _publish(
        tmp_path / "compiled-replacement",
        (("home", target_root, "claude"),),
        (("home", "claude", "replacement.json", b"replacement"),),
    )
    state_path = tmp_path / "state" / "apply-state.json"
    journal_path = Path(f"{state_path}.journal")
    manifest_snapshot = manifest_path.parent / "generations" / manifest.generation / "manifest.json"
    prepare_journal(
        journal_path,
        generation=manifest.generation,
        manifest_path=manifest_snapshot,
        manifest_sha256=hashlib.sha256(manifest_snapshot.read_bytes()).hexdigest(),
        previous_managed=(),
        desired_managed=(target_root / "a", target_root / "a" / "b"),
    )

    with pytest.raises(ProfileApplyError, match="ancestor/descendant"):
        apply_profile(replacement_manifest, state_path=state_path)

    assert not (target_root / "a").exists()
    assert not (target_root / "replacement.json").exists()
    assert journal_path.exists()


def test_apply_rejects_destination_control_alias_before_journal(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_path, _ = _publish(
        tmp_path / "compiled",
        (("home", target_root, "claude"),),
        (("home", "claude", "new.json", b"new"),),
    )
    state_path = target_root / "new.json"
    journal_path = Path(f"{state_path}.journal")

    with pytest.raises(ProfileApplyError, match="reserved control path"):
        apply_profile(manifest_path, state_path=state_path)

    assert not state_path.exists()
    assert not journal_path.exists()
