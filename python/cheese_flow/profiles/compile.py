"""Compile resolved profiles into immutable, content-addressed publications."""

from __future__ import annotations

import filecmp
import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .drift import FileComparison, compute_drift
from .errors import ProfileCompileError
from .generation import bind_generation, generation_descriptor, publish_generation
from .manifest_codec import load_manifest
from .models import CompiledFile, CompiledProfileManifest, CompileRequest, CompileTarget
from .renderers.registry import renderer
from .source import ResolvedProfile, load_profile


def compile_profile(
    request: CompileRequest,
    *,
    environment: Mapping[str, str],
) -> CompiledProfileManifest:
    """Render one profile privately, then atomically publish its generation."""
    env = dict(environment)
    output_root = Path(request.output_root)
    source_root = Path(request.source_root)
    baseline_root = Path(request.baseline_root)
    _reject_output_intersections(
        output_root,
        (
            ("source root", source_root),
            ("baseline root", baseline_root),
        ),
    )
    profile = load_profile(source_root, request.profile_name, environment=env)
    targets = profile.compile_targets
    if not targets:
        raise ProfileCompileError(f"profile {request.profile_name!r} must define compile_targets")

    _reject_output_intersections(
        output_root,
        tuple(("live target", target.resolved_root) for target in targets),
    )
    _reject_baseline_tree(baseline_root)
    baseline_root = baseline_root.resolve(strict=False)

    with tempfile.TemporaryDirectory(prefix="cheese-flow-profile-") as scratch_dir:
        files, drift, payloads = _render_targets(
            profile,
            targets,
            baseline_root=baseline_root,
            scratch_root=Path(scratch_dir),
            home=env.get("HOME"),
        )
    _validate_destination_set(files, targets)

    try:
        descriptor = generation_descriptor(
            schema_version=1,
            profile=profile.name,
            source_id=profile.source_id,
            compile_targets=targets,
            files=files,
            drift=drift,
        )
        manifest = bind_generation(descriptor)
        manifest_path = publish_generation(output_root, manifest, payloads)
        return load_manifest(manifest_path)
    except ProfileCompileError:
        raise
    except Exception as exc:
        raise ProfileCompileError(
            f"failed to publish compiled profile {profile.name!r}: {exc}"
        ) from exc


def _render_targets(
    profile: ResolvedProfile,
    targets: tuple[CompileTarget, ...],
    *,
    baseline_root: Path,
    scratch_root: Path,
    home: str | None,
) -> tuple[tuple[CompiledFile, ...], tuple, dict[PurePosixPath, bytes]]:
    candidates: dict[
        tuple[str, PurePosixPath],
        list[tuple[CompiledFile, FileComparison, bytes]],
    ] = {}
    for target_index, target in enumerate(targets):
        target_baseline = _map_target_to_baseline(baseline_root, target, home)
        for harness_index, harness in enumerate(target.harnesses):
            work = scratch_root / f"work-{target_index}-{harness_index}"
            _copy_to_scratch(target_baseline, work)
            try:
                renderer(harness).render(profile, work, logical_root=target.resolved_root)
            except ProfileCompileError:
                raise
            except Exception as exc:
                raise ProfileCompileError(
                    f"renderer {harness!r} failed for target {target.name!r} "
                    f"while compiling profile {profile.name!r}: {exc}"
                ) from exc
            changed = _changed_files(target_baseline, work)
            target_files, target_comparisons, target_payloads = _capture_files(
                target,
                harness,
                target_baseline,
                work,
                changed,
            )
            for compiled_file, comparison in zip(target_files, target_comparisons, strict=True):
                candidates.setdefault((target.name, compiled_file.destination_path), []).append(
                    (
                        compiled_file,
                        comparison,
                        target_payloads[compiled_file.fragment_path],
                    )
                )

    files: list[CompiledFile] = []
    comparisons: list[FileComparison] = []
    payloads: dict[PurePosixPath, bytes] = {}
    for (target_name, destination), output_candidates in sorted(
        candidates.items(),
        key=lambda item: (item[0][0], item[0][1].as_posix()),
    ):
        selected = min(output_candidates, key=lambda item: item[0].harness)
        selected_file, selected_comparison, selected_payload = selected
        for candidate_file, _, candidate_payload in output_candidates:
            if candidate_payload != selected_payload or candidate_file.mode != selected_file.mode:
                raise ProfileCompileError(
                    f"conflicting renderer outputs for target {target_name!r} "
                    f"destination {destination.as_posix()!r}"
                )
        files.append(selected_file)
        comparisons.append(selected_comparison)
        payloads[selected_file.fragment_path] = selected_payload
    return tuple(files), tuple(compute_drift(comparisons)), payloads


def _validate_destination_set(
    files: tuple[CompiledFile, ...],
    targets: tuple[CompileTarget, ...],
) -> None:
    roots = {target.name: target.resolved_root for target in targets}
    destinations = sorted(
        [
            (
                roots[compiled_file.target].joinpath(*compiled_file.destination_path.parts),
                compiled_file.target,
                compiled_file.destination_path,
            )
            for compiled_file in files
        ],
        key=lambda item: (item[0].as_posix(), item[1], item[2].as_posix()),
    )
    for index, (destination, target, relative) in enumerate(destinations):
        for prior_destination, prior_target, prior_relative in destinations[:index]:
            if destination == prior_destination:
                raise ProfileCompileError(
                    f"duplicate compiled destination {destination} "
                    f"from targets {prior_target!r} and {target!r}"
                )
            try:
                destination.relative_to(prior_destination)
            except ValueError:
                continue
            raise ProfileCompileError(
                f"compiled destination prefix conflict: {prior_target!r} "
                f"{prior_relative.as_posix()!r} contains {target!r} "
                f"{relative.as_posix()!r}"
            )


def _capture_files(
    target: CompileTarget,
    harness: str,
    target_baseline: Path,
    work: Path,
    changed: tuple[PurePosixPath, ...],
) -> tuple[list[CompiledFile], list[FileComparison], dict[PurePosixPath, bytes]]:
    files: list[CompiledFile] = []
    comparisons: list[FileComparison] = []
    payloads: dict[PurePosixPath, bytes] = {}
    for destination in changed:
        source = work.joinpath(*destination.parts)
        if source.is_symlink() or not source.is_file():
            raise ProfileCompileError(f"generated path is not a regular file: {source}")
        payload = source.read_bytes()
        fragment = PurePosixPath(target.name, harness, *destination.parts)
        files.append(
            CompiledFile(
                target=target.name,
                harness=harness,
                fragment_path=fragment,
                destination_path=destination,
                sha256=hashlib.sha256(payload).hexdigest(),
                mode=stat.S_IMODE(source.stat().st_mode),
            )
        )
        comparisons.append(
            FileComparison(
                target=target.name,
                destination_path=destination,
                baseline=target_baseline.joinpath(*destination.parts),
                live=target.resolved_root.joinpath(*destination.parts),
                compiled=source,
            )
        )
        payloads[fragment] = payload
    return files, comparisons, payloads


def _copy_to_scratch(source: Path, destination: Path) -> None:
    _reject_baseline_tree(source)
    if source.exists():
        if not source.is_dir():
            raise ProfileCompileError(f"baseline target is not a directory: {source}")
        shutil.copytree(source, destination)
        return
    destination.mkdir(parents=True, exist_ok=True)


def _reject_symlink_components(path: Path, *, kind: str) -> None:
    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        try:
            is_link = current.is_symlink()
            exists = current.exists()
        except OSError as exc:
            raise ProfileCompileError(f"could not inspect {kind}: {current}") from exc
        if is_link:
            raise ProfileCompileError(f"{kind} contains a symlink boundary: {current}")
        if not exists:
            break


def _reject_baseline_tree(root: Path) -> None:
    _reject_symlink_components(root, kind="baseline")
    if not root.exists():
        return
    if not root.is_dir():
        raise ProfileCompileError(f"baseline target is not a directory: {root}")
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            child = Path(current) / name
            if child.is_symlink():
                raise ProfileCompileError(f"baseline contains a symlink: {child}")


def _changed_files(before: Path, after: Path) -> tuple[PurePosixPath, ...]:
    changed: list[PurePosixPath] = []
    for path in sorted(after.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ProfileCompileError(f"generated path is a symlink: {path}")
        if not path.is_file():
            continue
        relative = PurePosixPath(*path.relative_to(after).parts)
        prior = before.joinpath(*relative.parts)
        if (
            not prior.is_file()
            or not filecmp.cmp(path, prior, shallow=False)
            or stat.S_IMODE(path.stat().st_mode) != stat.S_IMODE(prior.stat().st_mode)
        ):
            changed.append(relative)
    return tuple(changed)


def _map_target_to_baseline(
    baseline_root: Path,
    target: CompileTarget,
    home: str | None,
) -> Path:
    if home:
        home_path = Path(home).resolve(strict=False)
        try:
            relative = target.resolved_root.relative_to(home_path)
        except ValueError:
            pass
        else:
            return baseline_root.joinpath(*relative.parts)

    named = baseline_root / target.name
    return named if named.exists() else baseline_root


def _paths_intersect(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _reject_output_intersections(
    output_root: Path,
    roots: tuple[tuple[str, Path], ...],
) -> None:
    output = output_root.resolve(strict=False)
    for kind, root in roots:
        candidate = Path(root).resolve(strict=False)
        if _paths_intersect(output, candidate):
            raise ProfileCompileError(f"output_root intersects {kind}: {candidate}")


__all__ = ["compile_profile"]
