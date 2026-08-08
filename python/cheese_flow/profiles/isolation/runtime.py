"""Lifecycle helpers for isolated profile launch workspaces.

Launch construction happens before the CLI hands control to a harness, so a
workspace cannot be managed by a context manager: successful construction
must leave the workspace available to the eventual child process.  Callers
remove it only when the child cannot be executed.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

from cheese_flow.profiles.errors import ProfileLaunchError


class WorkspaceCleanupError(ProfileLaunchError):
    """Report a failed build together with its failed workspace cleanup."""


def _safe_exception_message(error: BaseException, environment: Mapping[str, str]) -> str:
    message = str(error) or type(error).__name__
    try:
        values = tuple(environment.values())
    except Exception:
        values = ()
    for value in values:
        if isinstance(value, str) and value:
            message = message.replace(value, "<redacted>")
    return message


_WORKSPACE_PARENT = Path("cheese-flow") / "profile-launch"
_WORKSPACE_MODE = 0o700
_FILE_MODE = 0o600


def _absolute_environment_path(environment: Mapping[str, str], name: str) -> Path | None:
    """Return one valid absolute path from the explicit launch environment."""
    value = environment.get(name)
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return None
    return path if path.is_absolute() else None


def _runtime_directory(environment: Mapping[str, str]) -> Path | None:
    """Return a usable explicit runtime directory, if one is provided."""
    path = _absolute_environment_path(environment, "XDG_RUNTIME_DIR")
    if path is None:
        return None
    if not _symlink_free_directory(path):
        return None
    try:
        return path if path.is_dir() and os.access(path, os.W_OK | os.X_OK) else None
    except OSError:
        return None


def _cache_directories(environment: Mapping[str, str]) -> tuple[Path, ...]:
    """Return explicit cache fallbacks in their required precedence order."""
    candidates: list[Path] = []
    cache = _absolute_environment_path(environment, "XDG_CACHE_HOME")
    if cache is not None:
        candidates.append(cache)
    home = _absolute_environment_path(environment, "HOME")
    if home is not None:
        candidates.append(home / ".cache")
    return tuple(candidates)


def _symlink_free_directory(path: Path) -> bool:
    """Check every existing component with ``lstat`` without following links."""
    if not path.is_absolute():
        return False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            return False
    return True


def _try_allocate(parent: Path) -> Path | None:
    """Create one private parent and one private unique workspace."""
    workspace: Path | None = None
    launch_parent = parent / _WORKSPACE_PARENT
    if not _symlink_free_directory(launch_parent):
        return None
    try:
        launch_parent.mkdir(parents=True, exist_ok=True, mode=_WORKSPACE_MODE)
        if not _symlink_free_directory(launch_parent):
            return None
        os.chmod(launch_parent, _WORKSPACE_MODE)
        workspace = Path(tempfile.mkdtemp(prefix=".launch-", dir=launch_parent))
        if not _symlink_free_directory(workspace):
            raise OSError("workspace is not a directory")
        os.chmod(workspace, _WORKSPACE_MODE)
        return workspace
    except (OSError, RuntimeError, ValueError):
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)
        return None


def allocate_workspace(environment: Mapping[str, str]) -> Path:
    """Allocate one unique private workspace using only ``environment``.

    ``XDG_RUNTIME_DIR`` is used only when it already names a writable
    directory.  Cache and home fallbacks may be created as needed.  No value
    from the environment is included in an allocation error.
    """
    parents: list[Path] = []
    runtime = _runtime_directory(environment)
    if runtime is not None:
        parents.append(runtime)
    parents.extend(_cache_directories(environment))

    for parent in parents:
        workspace = _try_allocate(parent)
        if workspace is not None:
            return workspace
    raise RuntimeError("could not allocate a private launch workspace")


def _workspace_root(root: Path) -> Path:
    """Resolve and validate an existing workspace directory."""
    try:
        candidate = Path(root)
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("workspace root must be an existing directory") from None
    if not resolved.is_dir():
        raise ValueError("workspace root must be an existing directory")
    return resolved


def _relative_file_parts(relative_path: str | os.PathLike[str]) -> tuple[str, ...]:
    """Validate one relative POSIX file identity without touching the host."""
    try:
        raw = os.fspath(relative_path)
    except TypeError:
        raise ValueError("workspace file path must be relative") from None
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValueError("workspace file path must be relative")
    path = PurePosixPath(raw)
    if path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts:
        raise ValueError("workspace file path must stay within the workspace")
    return path.parts


def _contained_path(root: Path, parts: tuple[str, ...]) -> Path:
    """Resolve one workspace child and reject symlink or lexical escapes."""
    current = root
    try:
        for part in parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise ValueError("workspace file path must stay within the workspace")
            if current.exists() and not current.is_dir():
                raise ValueError("workspace file path must stay within the workspace")
            current.mkdir(exist_ok=True, mode=_WORKSPACE_MODE)
            os.chmod(current, _WORKSPACE_MODE)

        candidate = root.joinpath(*parts)
        if candidate.is_symlink() or (candidate.exists() and candidate.is_dir()):
            raise ValueError("workspace file path must stay within the workspace")
        parent = candidate.parent.resolve(strict=True)
        parent.relative_to(root)
        candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        raise
    except (OSError, RuntimeError):
        raise ValueError("workspace file path must stay within the workspace") from None
    return candidate


def write_workspace_file(
    root: Path,
    relative_path: str | os.PathLike[str],
    content: str | bytes | bytearray | memoryview,
) -> Path:
    """Write one generated file beneath ``root`` with mode ``0600``."""
    if not isinstance(content, (str, bytes, bytearray, memoryview)):
        raise TypeError("workspace file content must be text or bytes")
    workspace = _workspace_root(root)
    candidate = _contained_path(workspace, _relative_file_parts(relative_path))
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags, _FILE_MODE)
        if isinstance(content, str):
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
        else:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(bytes(content))
        os.chmod(candidate, _FILE_MODE)
    except OSError:
        raise RuntimeError("could not write launch workspace file") from None
    return candidate


def remove_workspace(root: Path) -> None:
    """Remove one workspace, treating an already-removed root as success."""
    try:
        candidate = Path(root)
    except (TypeError, ValueError):
        raise ValueError("workspace root must be a directory") from None
    if not candidate.exists():
        return
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("workspace root must be a directory")
    try:
        shutil.rmtree(candidate)
    except OSError:
        raise RuntimeError("could not remove launch workspace") from None


def build_workspace(
    environment: Mapping[str, str],
    builder: Callable[[Path], None],
) -> Path:
    """Build a complete workspace and clean it up only when ``builder`` fails."""
    root = allocate_workspace(environment)
    try:
        builder(root)
    except BaseException as primary:
        try:
            remove_workspace(root)
        except BaseException as cleanup:
            message = (
                f"{_safe_exception_message(primary, environment)}; "
                "workspace cleanup failed: "
                f"{_safe_exception_message(cleanup, environment)}"
            )
            raise WorkspaceCleanupError(message) from None
        raise
    return root


__all__ = [
    "allocate_workspace",
    "build_workspace",
    "WorkspaceCleanupError",
    "remove_workspace",
    "write_workspace_file",
]
