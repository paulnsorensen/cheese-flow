"""Manifest and filesystem validation for profile apply operations."""

from __future__ import annotations

import hashlib
import re
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ProfileApplyError
from .generation import validate_generation_binding
from .manifest_codec import load_manifest
from .models import CompiledProfileManifest, ProfileApplyState

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_GENERATIONS = PurePosixPath("generations")


class PlannedReplacement(BaseModel):
    """One validated fragment replacement in a live target tree."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_root: Path
    destination: Path
    content: bytes = Field(repr=False)
    sha256: str
    mode: int = 0o600

    @field_validator("target_root", "destination")
    @classmethod
    def _paths_are_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("planned replacement paths must be absolute")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha256_is_lowercase_hex(cls, value: str) -> str:
        if _HASH_RE.fullmatch(value) is None:
            raise ValueError(
                "planned replacement sha256 must be 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("mode", mode="before")
    @classmethod
    def _mode_is_private_posix_integer(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0o777:
            raise ValueError(
                "planned replacement mode must be an integer POSIX mode from 0 to 0o777"
            )
        return value


class PreflightPlan(BaseModel):
    """Complete, mutation-free apply plan produced from one manifest generation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generation: str
    target_roots: tuple[Path, ...]
    replacements: tuple[PlannedReplacement, ...]
    stale_files: tuple[Path, ...]
    managed_files: tuple[Path, ...]

    @field_validator("generation")
    @classmethod
    def _generation_is_lowercase_sha256(cls, value: str) -> str:
        if _HASH_RE.fullmatch(value) is None:
            raise ValueError("generation must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("target_roots", "stale_files", "managed_files")
    @classmethod
    def _ownership_paths_are_absolute(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        relative = tuple(str(path) for path in value if not path.is_absolute())
        if relative:
            raise ValueError(f"ownership paths must be absolute: {', '.join(relative)}")
        return value


class _TargetRoots:
    """Canonical target lookup kept private to preflight validation."""

    def __init__(
        self,
        roots: Mapping[str, Path],
        harnesses: Mapping[str, frozenset[str]],
    ) -> None:
        self.roots = dict(roots)
        self.harnesses = dict(harnesses)


def _error(message: str, cause: BaseException | None = None) -> ProfileApplyError:
    error = ProfileApplyError(message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _lexical_absolute(path: Path) -> Path:
    raw_path = Path(path)
    if raw_path.is_absolute():
        return raw_path
    try:
        return Path.cwd() / raw_path
    except OSError as exc:
        raise _error(f"could not make path absolute: {raw_path}", exc) from exc


def _check_lexical_components(path: Path, *, kind: str) -> None:
    """Reject symlink boundaries while retaining the path's lexical spelling."""

    lexical = _lexical_absolute(path)
    current = Path(lexical.anchor or "/")
    parts = lexical.parts[1:] if lexical.anchor else lexical.parts
    for part in parts:
        if part in {"", "."}:
            continue
        current /= part
        try:
            is_link = current.is_symlink()
            exists = current.exists()
        except OSError as exc:
            raise _error(f"could not inspect {kind}: {current}", exc) from exc
        if is_link:
            raise _error(f"{kind} contains a symlink boundary: {current}")
        if not exists:
            break
        if current != lexical and not current.is_dir():
            raise _error(f"{kind} parent is not a directory: {current}")


def _validate_control_path(
    path: Path,
    *,
    kind: str,
    require_regular_file: bool = False,
) -> Path:
    """Validate one control path without following a lexical symlink boundary."""

    lexical = _lexical_absolute(Path(path))
    _check_lexical_components(lexical, kind=kind)
    try:
        resolved = lexical.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _error(f"could not resolve {kind}: {lexical}", exc) from exc
    if resolved != lexical:
        raise _error(f"{kind} is not a canonical lexical path: {lexical}")
    if require_regular_file:
        try:
            info = lexical.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise _error(f"could not inspect {kind}: {lexical}", exc) from exc
        else:
            if not stat.S_ISREG(info.st_mode):
                raise _error(f"{kind} is not a regular file: {lexical}")
    return resolved


def _path_alias(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _temporary_control_alias(path: Path, control: Path) -> bool:
    return (
        path.parent == control.parent
        and path.name.startswith(f".{control.name}.")
        and path.name.endswith(".tmp")
    )


def _control_alias(path: Path, control: Path) -> bool:
    return (
        _path_alias(path, control)
        or _temporary_control_alias(path, control)
        or _temporary_control_alias(control, path)
    )


def _reject_prefix_conflicts(paths: tuple[Path, ...], *, kind: str) -> None:
    ordered = sorted(paths, key=lambda path: (len(path.parts), path.as_posix()))
    for index, candidate in enumerate(ordered):
        for ancestor in ordered[:index]:
            if ancestor in candidate.parents:
                raise _error(
                    f"{kind} contains an ancestor/descendant conflict: {ancestor} and {candidate}"
                )


def _reject_structural_ownership_conflicts(
    previous: tuple[Path, ...],
    desired: tuple[Path, ...],
) -> None:
    for prior in previous:
        for target in desired:
            if prior != target and (prior in target.parents or target in prior.parents):
                raise _error(
                    f"stale and desired ownership paths have an ancestor/descendant conflict: "
                    f"{prior} and {target}"
                )


def _manifest_output_root(manifest_file: Path, manifest: CompiledProfileManifest) -> Path:
    generation_root = manifest_file.parent
    if (
        generation_root.name == manifest.generation
        and generation_root.parent.name == _GENERATIONS.name
    ):
        return generation_root.parent.parent
    return generation_root


def _reserved_control_paths(
    manifest_file: Path,
    manifest: CompiledProfileManifest,
    reserved_paths: Mapping[str, Path] | None,
) -> tuple[tuple[str, Path], ...]:
    fragment_root = _manifest_output_root(manifest_file, manifest)
    controls: list[tuple[str, Path]] = [("manifest", manifest_file)]
    if fragment_root != manifest_file.parent:
        controls.append(
            (
                "latest manifest",
                _validate_control_path(
                    fragment_root / "manifest.json",
                    kind="latest profile manifest",
                    require_regular_file=True,
                ),
            )
        )
    for compiled_file in manifest.files:
        fragment_path = PurePosixPath(compiled_file.fragment_path)
        parts = _relative_parts(fragment_path, kind="fragment path")
        candidate = fragment_root.joinpath(*parts)
        controls.append(
            (
                f"fragment {fragment_path}",
                _validate_control_path(
                    candidate,
                    kind=f"fragment path {fragment_path}",
                    require_regular_file=True,
                ),
            )
        )
    if reserved_paths is not None:
        if not isinstance(reserved_paths, Mapping):
            raise _error("reserved apply control paths must be a mapping")
        for label, path in reserved_paths.items():
            if not isinstance(label, str) or not label:
                raise _error("reserved apply control path labels must be non-empty strings")
            controls.append(
                (
                    label,
                    _validate_control_path(
                        Path(path),
                        kind=f"profile apply control path {label!r}",
                        require_regular_file=True,
                    ),
                )
            )

    for index, (left_label, left_path) in enumerate(controls):
        for right_label, right_path in controls[index + 1 :]:
            if _control_alias(left_path, right_path):
                raise _error(
                    f"profile apply control paths conflict: "
                    f"{left_label} ({left_path}) and {right_label} ({right_path})"
                )
    return tuple(controls)


def _manifest_file(path: Path) -> Path:
    try:
        resolved = _validate_control_path(
            path,
            kind="profile manifest",
            require_regular_file=True,
        ).resolve(strict=True)
    except ProfileApplyError:
        raise
    except (OSError, RuntimeError) as exc:
        raise _error(f"profile manifest is not usable: {path}", exc) from exc
    if not resolved.is_file():
        raise _error(f"profile manifest is not a file: {path}")
    return resolved


def _target_name(name: object) -> str:
    if not isinstance(name, str) or not name or name in {".", ".."}:
        raise _error("compile target name must be a non-empty name")
    if "/" in name or "\\" in name:
        raise _error(f"compile target name must not contain path separators: {name!r}")
    return name


def _canonical_target_roots(manifest: CompiledProfileManifest) -> _TargetRoots:
    roots: dict[str, Path] = {}
    target_harnesses: dict[str, frozenset[str]] = {}
    harness_owners: dict[str, str] = {}
    for target in manifest.compile_targets:
        name = _target_name(target.name)
        if name in roots:
            raise _error(f"manifest has duplicate compile target {name!r}")
        if not target.harnesses:
            raise _error(f"compile target {name!r} has no harnesses")
        if len(set(target.harnesses)) != len(target.harnesses):
            raise _error(f"compile target {name!r} has duplicate harnesses")
        for harness in target.harnesses:
            owner = harness_owners.get(harness)
            if owner is not None:
                raise _error(f"harness {harness!r} is owned by both {owner!r} and {name!r}")
            harness_owners[harness] = name
        raw_root = Path(target.resolved_root)
        if not raw_root.is_absolute():
            raise _error(f"compile target {name!r} root must be absolute")
        root = _validate_control_path(
            raw_root,
            kind=f"compile target {name!r} root",
        )
        if root.exists() and not root.is_dir():
            raise _error(f"compile target {name!r} root is not a directory: {raw_root}")
        roots[name] = root
        target_harnesses[name] = frozenset(target.harnesses)
    return _TargetRoots(roots, target_harnesses)


def _relative_parts(path: PurePosixPath, *, kind: str) -> tuple[str, ...]:
    if path.is_absolute() or not path.parts or path == PurePosixPath("."):
        raise _error(f"{kind} must be a non-empty relative path")
    if ".." in path.parts:
        raise _error(f"{kind} must not contain '..' path components")
    return path.parts


def _ensure_within(candidate: Path, root: Path, *, kind: str, strict: bool = False) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _error(f"could not resolve {kind}: {candidate}", exc) from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise _error(f"{kind} escapes its root: {candidate}", exc) from exc
    if strict and not relative.parts:
        raise _error(f"{kind} must be a strict descendant of its root: {candidate}")
    return resolved


def _check_existing_components(root: Path, candidate: Path, *, kind: str) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise _error(f"{kind} escapes its root: {candidate}", exc) from exc
    current = root
    for part in relative.parts:
        current /= part
        try:
            is_link = current.is_symlink()
            exists = current.exists()
        except OSError as exc:
            raise _error(f"could not inspect {kind}: {current}", exc) from exc
        if is_link:
            raise _error(f"{kind} contains a symlink boundary: {current}")
        if not exists:
            break
        if current != candidate and not current.is_dir():
            raise _error(f"{kind} parent is not a directory: {current}")


def _destination(root: Path, relative: PurePosixPath, *, kind: str) -> Path:
    parts = _relative_parts(relative, kind=kind)
    candidate = root.joinpath(*parts)
    _check_lexical_components(candidate, kind=kind)
    _check_existing_components(root, candidate, kind=kind)
    resolved = _ensure_within(candidate, root, kind=kind, strict=True)
    if candidate.is_symlink():
        raise _error(f"{kind} is a symlink: {candidate}")
    if candidate.exists() and not candidate.is_file():
        raise _error(f"{kind} is not a regular file: {candidate}")
    return resolved


def _fragment(
    root: Path,
    manifest: CompiledProfileManifest,
    relative: PurePosixPath,
) -> bytes:
    parts = _relative_parts(relative, kind="fragment path")
    prefix = (_GENERATIONS / manifest.generation).parts
    if parts[: len(prefix)] != prefix or len(parts) <= len(prefix):
        raise _error(f"fragment path {relative} must start with generations/{manifest.generation}/")
    candidate = root.joinpath(*parts)
    _check_lexical_components(candidate, kind="fragment path")
    _check_existing_components(root, candidate, kind="fragment path")
    _ensure_within(candidate, root, kind="fragment path", strict=True)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            raise _error(f"fragment path is not a regular file: {candidate}")
        content = candidate.read_bytes()
    except OSError as exc:
        raise _error(f"could not read fragment {candidate}", exc) from exc
    return content


def _validate_prior_state(
    previous_state: ProfileApplyState | None,
    targets: _TargetRoots,
) -> tuple[Path, ...]:
    if previous_state is None:
        return ()
    try:
        state = (
            previous_state
            if isinstance(previous_state, ProfileApplyState)
            else ProfileApplyState.model_validate(previous_state)
        )
    except (TypeError, ValidationError) as exc:
        raise _error("profile apply state is malformed", exc) from exc

    owned: list[Path] = []
    seen: set[Path] = set()
    for raw_path in state.managed_files:
        path = Path(raw_path)
        if not path.is_absolute():
            raise _error(f"prior owned path must be absolute: {path}")
        _check_lexical_components(path, kind="prior owned path")
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise _error(f"could not resolve prior owned path: {path}", exc) from exc
        root = next(
            (
                root
                for root in targets.roots.values()
                if resolved != root and root in resolved.parents
            ),
            None,
        )
        if root is None:
            raise _error(f"prior owned path is outside every compile target: {path}")
        _ensure_within(path, root, kind="prior owned path", strict=True)
        if path.exists() and not path.is_file():
            raise _error(f"prior owned path is not a regular file: {path}")
        if resolved in seen:
            raise _error(f"prior ownership contains duplicate path: {path}")
        seen.add(resolved)
        owned.append(resolved)
    owned_paths = tuple(sorted(owned, key=lambda path: path.as_posix()))
    _reject_prefix_conflicts(owned_paths, kind="prior ownership")
    return owned_paths


def revalidate_parent_chain(destination: Path, target_root: Path) -> None:
    """Recheck the live parent chain immediately before one filesystem mutation."""

    raw_root = Path(target_root)
    raw_destination = Path(destination)
    if not raw_root.is_absolute() or not raw_destination.is_absolute():
        raise _error("target root and destination must be absolute")
    root = _validate_control_path(raw_root, kind="target root")
    if root.exists() and not root.is_dir():
        raise _error(f"target root is not a directory: {raw_root}")
    _check_lexical_components(raw_destination, kind="destination")
    try:
        lexical_relative = raw_destination.relative_to(root)
    except ValueError:
        lexical_relative = None
    else:
        if ".." in lexical_relative.parts:
            raise _error(f"destination must not contain '..' path components: {raw_destination}")
        _check_existing_components(root, raw_destination, kind="destination")
    try:
        resolved = raw_destination.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _error(f"could not resolve destination: {raw_destination}", exc) from exc
    relative = _ensure_within(
        resolved,
        root,
        kind="destination",
        strict=True,
    ).relative_to(root)
    if ".." in relative.parts:
        raise _error(f"destination must not contain '..' path components: {raw_destination}")
    if resolved.exists() and not resolved.is_file():
        raise _error(f"destination is not a regular file: {resolved}")


def preflight_apply(
    manifest_path: Path,
    previous_state: ProfileApplyState | None,
    *,
    reserved_paths: Mapping[str, Path] | None = None,
) -> PreflightPlan:
    """Validate one immutable generation and return a mutation-free apply plan."""

    manifest_file = _manifest_file(Path(manifest_path))
    try:
        manifest = load_manifest(manifest_file)
    except (OSError, UnicodeError, ValueError, TypeError, ValidationError) as exc:
        raise _error(f"profile manifest is malformed: {manifest_file}", exc) from exc
    try:
        manifest = validate_generation_binding(manifest)
    except (ValueError, TypeError, ValidationError) as exc:
        raise _error(
            f"profile manifest generation binding is invalid: {manifest_file}",
            exc,
        ) from exc

    targets = _canonical_target_roots(manifest)
    fragment_root = _manifest_output_root(manifest_file, manifest)
    controls = _reserved_control_paths(manifest_file, manifest, reserved_paths)
    prior = _validate_prior_state(previous_state, targets)
    replacements: list[PlannedReplacement] = []
    destinations: dict[Path, str] = {}
    fragments: dict[PurePosixPath, str] = {}
    destination_cache: dict[tuple[str, PurePosixPath], Path] = {}
    drift_keys: set[tuple[str, Path, str]] = set()

    for drift in manifest.drift:
        if drift.target not in targets.roots:
            raise _error(f"drift record references unknown target: {drift.target!r}")
        destination_key = (drift.target, drift.destination_path)
        drift_destination = destination_cache.get(destination_key)
        if drift_destination is None:
            drift_destination = _destination(
                targets.roots[drift.target],
                drift.destination_path,
                kind="drift destination",
            )
            destination_cache[destination_key] = drift_destination
        drift_key = (drift.target, drift_destination, drift.path)
        if drift_key in drift_keys:
            raise _error(
                "manifest has duplicate drift record "
                f"({drift.target!r}, {drift_destination}, {drift.path!r})"
            )
        drift_keys.add(drift_key)

    for compiled_file in manifest.files:
        target = compiled_file.target
        if target not in targets.roots:
            raise _error(f"file references unknown target: {target!r}")
        if compiled_file.harness not in targets.harnesses[target]:
            raise _error(
                f"file references harness {compiled_file.harness!r} not owned by target {target!r}"
            )
        fragment_path = PurePosixPath(compiled_file.fragment_path)
        if fragment_path in fragments:
            raise _error(f"manifest has duplicate fragment path: {fragment_path}")
        fragments[fragment_path] = target
        content = _fragment(fragment_root, manifest, fragment_path)
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != compiled_file.sha256:
            raise _error(
                f"fragment hash mismatch for {fragment_path}: "
                f"expected {compiled_file.sha256}, got {actual_hash}"
            )
        destination_key = (target, compiled_file.destination_path)
        destination = destination_cache.get(destination_key)
        if destination is None:
            destination = _destination(
                targets.roots[target],
                compiled_file.destination_path,
                kind="destination",
            )
            destination_cache[destination_key] = destination
        prior_target = destinations.get(destination)
        if prior_target is not None:
            raise _error(
                f"manifest has duplicate destination {destination} "
                f"({prior_target!r} and {target!r})"
            )
        destinations[destination] = target
        replacements.append(
            PlannedReplacement(
                target_root=targets.roots[target],
                destination=destination,
                content=content,
                sha256=compiled_file.sha256,
                mode=compiled_file.mode,
            )
        )

    replacements.sort(key=lambda replacement: replacement.destination.as_posix())
    managed = tuple(replacement.destination for replacement in replacements)
    _reject_prefix_conflicts(managed, kind="desired destinations")
    _reject_structural_ownership_conflicts(prior, managed)
    managed_set = set(managed)
    stale = tuple(path for path in prior if path not in managed_set)
    for ownership_kind, paths in (("desired", managed), ("stale", stale)):
        for path in paths:
            for control_label, control_path in controls:
                if _control_alias(path, control_path):
                    raise _error(
                        f"{ownership_kind} path aliases reserved control path "
                        f"{control_label}: {path}"
                    )
    return PreflightPlan(
        generation=manifest.generation,
        target_roots=tuple(sorted(targets.roots.values(), key=lambda path: path.as_posix())),
        replacements=tuple(replacements),
        stale_files=stale,
        managed_files=managed,
    )


__all__ = [
    "PlannedReplacement",
    "PreflightPlan",
    "preflight_apply",
    "revalidate_parent_chain",
]
