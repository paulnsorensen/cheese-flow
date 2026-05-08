"""Verbatim port of `tests/harness-detection.test.ts`.

The TS suite mutates `process.platform` and `process.env.PATH/Path/PATHEXT`
to exercise win32 PATHEXT branches and the PATH/Path fallback. Python uses
`monkeypatch` for env mutation and patches `sys.platform` (which the
implementation reads) for the win32 branches.
"""

from __future__ import annotations

import asyncio
import stat
import uuid
from pathlib import Path

import pytest
from cheese_flow.lib import harness_detection
from cheese_flow.lib.harness_detection import (
    detect_available_harnesses,
    find_command_on_path,
    get_harness_install_capability,
)


def _make_directory(runtime_root: Path, prefix: str) -> Path:
    directory = runtime_root / f"{prefix}-{uuid.uuid4()}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_executable(directory: Path, name: str) -> Path:
    file_path = directory / name
    file_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf8")
    file_path.chmod(file_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return file_path


def test_get_harness_install_capability_classifies_harnesses_by_install_capability() -> None:
    assert get_harness_install_capability("claude-code") == "manual-capable"
    assert get_harness_install_capability("cursor") == "auto-install"


def test_find_command_on_path_falls_back_path_then_capital_path_then_none(  # noqa: E501 - long descriptive name
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_directory = _make_directory(tmp_path, "path-bin")
    executable_path = _write_executable(bin_directory, "copilot")

    monkeypatch.setenv("PATH", str(bin_directory))
    monkeypatch.delenv("Path", raising=False)
    assert asyncio.run(find_command_on_path("copilot")) == str(executable_path)

    monkeypatch.delenv("PATH", raising=False)
    monkeypatch.setenv("Path", str(bin_directory))
    assert asyncio.run(find_command_on_path("copilot")) == str(executable_path)

    monkeypatch.delenv("Path", raising=False)
    assert asyncio.run(find_command_on_path("copilot")) is None


def test_find_command_on_path_applies_win32_pathext_probes_and_preserves_explicit_extensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_directory = _make_directory(tmp_path, "win-bin")
    default_extension_path = _write_executable(bin_directory, "codex.COM")
    explicit_extension_path = _write_executable(bin_directory, "copilot.CMD")

    monkeypatch.delenv("PATHEXT", raising=False)
    monkeypatch.setattr(harness_detection.sys, "platform", "win32")

    assert asyncio.run(find_command_on_path("codex", str(bin_directory))) == str(
        default_extension_path
    )

    monkeypatch.setenv("PATHEXT", ".EXE;.CMD")
    assert asyncio.run(find_command_on_path("copilot", str(bin_directory))) == str(
        explicit_extension_path
    )
    assert asyncio.run(find_command_on_path("copilot.CMD", str(bin_directory))) == str(
        explicit_extension_path
    )


def test_detect_available_harnesses_uses_default_fs_and_path_probes(  # noqa: E501 - long descriptive name
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _make_directory(tmp_path, "project-root")
    bin_directory = _make_directory(tmp_path, "detect-bin")
    detected_command_path = _write_executable(bin_directory, "copilot")
    cursor_surface = project_root / ".cursor"
    cursor_surface.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PATH", str(bin_directory))
    monkeypatch.delenv("Path", raising=False)

    detections = asyncio.run(detect_available_harnesses(project_root=str(project_root)))

    assert detections["copilot-cli"]["state"] == "detected"
    assert detections["copilot-cli"]["kind"] == "cli"
    assert detections["copilot-cli"]["value"] == str(detected_command_path)

    assert detections["cursor"]["state"] == "detected"
    assert detections["cursor"]["kind"] == "surface"
    assert detections["cursor"]["value"] == str(cursor_surface)

    assert detections["claude-code"] == {
        "state": "not-detected",
        "reason": 'No Claude Code CLI "claude" on PATH detected.',
    }
    assert detections["codex"] == {
        "state": "not-detected",
        "reason": 'No Codex CLI "codex" on PATH detected.',
    }
