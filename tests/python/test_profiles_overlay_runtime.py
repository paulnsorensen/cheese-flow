"""Behavioral tests for isolated profile launch workspaces."""

from __future__ import annotations

from pathlib import Path
from stat import S_IMODE

import cheese_flow.profiles.isolation.runtime as runtime
import pytest
from cheese_flow.profiles.isolation.runtime import (
    WorkspaceCleanupError,
    allocate_workspace,
    build_workspace,
    remove_workspace,
    write_workspace_file,
)


def _mode(path: Path) -> int:
    return S_IMODE(path.stat().st_mode)


def _environment(tmp_path: Path) -> dict[str, str]:
    return {
        "XDG_RUNTIME_DIR": str(tmp_path / "runtime"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "HOME": str(tmp_path / "home"),
    }


def test_allocate_workspace_prefers_runtime_and_is_unique_private_and_retained(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    runtime = Path(environment["XDG_RUNTIME_DIR"])
    runtime.mkdir()

    first = allocate_workspace(environment)
    second = allocate_workspace(environment)
    try:
        assert first != second
        assert first.parent == runtime / "cheese-flow" / "profile-launch"
        assert _mode(first) == 0o700
        assert _mode(second) == 0o700
        assert first.is_dir() and second.is_dir()
    finally:
        remove_workspace(first)
        remove_workspace(second)


def test_allocate_workspace_falls_back_from_unusable_runtime_to_cache(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    runtime = Path(environment["XDG_RUNTIME_DIR"])
    runtime.write_text("not a directory")

    workspace = allocate_workspace(environment)
    try:
        assert workspace.parent == (
            Path(environment["XDG_CACHE_HOME"]) / "cheese-flow" / "profile-launch"
        )
        assert _mode(workspace) == 0o700
    finally:
        remove_workspace(workspace)


def test_allocate_workspace_rejects_symlinked_parent_components(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (cache / "cheese-flow").symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="private launch workspace"):
        allocate_workspace({"XDG_CACHE_HOME": str(cache)})

    assert not (target / "profile-launch").exists()


def test_write_workspace_file_enforces_containment_and_private_mode(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = allocate_workspace(environment)
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    try:
        generated = write_workspace_file(workspace, "nested/config.json", '{"enabled": true}\n')
        assert generated.read_text() == '{"enabled": true}\n'
        assert _mode(generated) == 0o600
        assert _mode(generated.parent) == 0o700

        with pytest.raises(ValueError, match="workspace"):
            write_workspace_file(workspace, "../outside.txt", "overwrite")
        assert outside.read_text() == "unchanged"

        (workspace / "escape").symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError, match="workspace"):
            write_workspace_file(workspace, "escape/secret.txt", "must not write")
        assert not (tmp_path / "secret.txt").exists()
    finally:
        remove_workspace(workspace)


def test_build_workspace_cleans_failed_build_but_retains_success(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    failed_root: list[Path] = []

    def fail(root: Path) -> None:
        failed_root.append(root)
        write_workspace_file(root, "partial.txt", b"partial")
        raise RuntimeError("builder failed")

    with pytest.raises(RuntimeError, match="builder failed"):
        build_workspace(environment, fail)

    assert failed_root and not failed_root[0].exists()

    retained = build_workspace(
        environment,
        lambda root: write_workspace_file(root, "complete.txt", "complete"),
    )
    try:
        assert retained.is_dir()
        assert (retained / "complete.txt").read_text() == "complete"
    finally:
        remove_workspace(retained)


def test_build_workspace_reports_build_and_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment(tmp_path)

    def fail_build(root: Path) -> None:
        write_workspace_file(root, "partial.txt", b"partial")
        raise RuntimeError("builder failed")

    def fail_cleanup(workspace: Path) -> None:
        raise RuntimeError(f"cleanup failed for {environment['HOME']}")

    monkeypatch.setattr(runtime, "remove_workspace", fail_cleanup)

    with pytest.raises(
        WorkspaceCleanupError, match="builder failed; workspace cleanup failed"
    ) as error:
        build_workspace(environment, fail_build)
    assert environment["HOME"] not in str(error.value)


def test_workspace_errors_do_not_echo_environment_values(tmp_path: Path) -> None:
    secret = "workspace-secret-value"
    environment = {
        "XDG_RUNTIME_DIR": f"{tmp_path / secret}\x00invalid",
        "XDG_CACHE_HOME": "relative-cache",
        "HOME": "relative-home",
    }

    with pytest.raises(RuntimeError) as error:
        allocate_workspace(environment)
    assert secret not in str(error.value)


def test_remove_workspace_is_idempotent(tmp_path: Path) -> None:
    workspace = allocate_workspace({"HOME": str(tmp_path / "home")})
    remove_workspace(workspace)
    remove_workspace(workspace)
    assert not workspace.exists()
