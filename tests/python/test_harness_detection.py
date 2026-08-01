"""Harness detection against a real, injected home directory and PATH."""

from __future__ import annotations

from pathlib import Path

import pytest
from cheese_flow.harness_detection import detect_available_harnesses


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME and PATH at empty temporary directories and return the home."""
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("USERPROFILE", raising=False)
    return home


def install_binary(name: str, tmp_path: Path) -> Path:
    executable = tmp_path / "bin" / name
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    return executable


def test_nothing_installed_detects_nothing(probe: Path, tmp_path: Path) -> None:
    assert detect_available_harnesses() == ()


def test_claude_cli_on_path_detects_claude_code(probe: Path, tmp_path: Path) -> None:
    install_binary("claude", tmp_path)

    assert detect_available_harnesses() == ("claude-code",)


def test_claude_config_directory_detects_claude_code(probe: Path, tmp_path: Path) -> None:
    (probe / ".claude").mkdir()

    assert detect_available_harnesses() == ("claude-code",)


def test_codex_cli_on_path_detects_codex(probe: Path, tmp_path: Path) -> None:
    install_binary("codex", tmp_path)

    assert detect_available_harnesses() == ("codex",)


def test_codex_config_directory_detects_codex(probe: Path, tmp_path: Path) -> None:
    (probe / ".codex").mkdir()

    assert detect_available_harnesses() == ("codex",)


def test_cursor_config_directory_detects_cursor(probe: Path, tmp_path: Path) -> None:
    (probe / ".cursor").mkdir()

    assert detect_available_harnesses() == ("cursor",)


def test_cursor_agent_cli_detects_cursor(probe: Path, tmp_path: Path) -> None:
    install_binary("cursor-agent", tmp_path)

    assert detect_available_harnesses() == ("cursor",)


def test_cursor_editor_cli_detects_cursor(probe: Path, tmp_path: Path) -> None:
    install_binary("cursor", tmp_path)

    assert detect_available_harnesses() == ("cursor",)


def test_symlinked_config_directory_still_counts(probe: Path, tmp_path: Path) -> None:
    real = tmp_path / "dotfiles" / "cursor"
    real.mkdir(parents=True)
    (probe / ".cursor").symlink_to(real, target_is_directory=True)

    assert detect_available_harnesses() == ("cursor",)


def test_config_path_that_is_a_file_is_not_a_signal(probe: Path, tmp_path: Path) -> None:
    (probe / ".claude").write_text("not a directory\n")

    assert detect_available_harnesses() == ()


def test_non_executable_file_on_path_is_not_a_signal(probe: Path, tmp_path: Path) -> None:
    dud = tmp_path / "bin" / "codex"
    dud.write_text("#!/bin/sh\n")
    dud.chmod(0o644)

    assert detect_available_harnesses() == ()


def test_detected_harnesses_are_returned_in_harness_name_order(probe: Path, tmp_path: Path) -> None:
    (probe / ".cursor").mkdir()
    install_binary("codex", tmp_path)
    (probe / ".claude").mkdir()

    assert detect_available_harnesses() == ("claude-code", "codex", "cursor")


def test_each_harness_is_reported_once_when_both_signals_are_present(
    probe: Path, tmp_path: Path
) -> None:
    (probe / ".claude").mkdir()
    install_binary("claude", tmp_path)

    assert detect_available_harnesses() == ("claude-code",)


def test_project_local_config_directories_are_not_a_detection_signal(
    probe: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".cursor").mkdir()
    monkeypatch.chdir(project)

    assert detect_available_harnesses() == ()


def test_detection_reports_the_same_harnesses_from_any_working_directory(
    probe: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Detection reads the user's home, not the cwd, so location cannot change it."""
    (probe / ".codex").mkdir()
    install_binary("claude", tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".cursor").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    from_root = detect_available_harnesses()
    monkeypatch.chdir(elsewhere)
    from_elsewhere = detect_available_harnesses()

    assert from_root == ("claude-code", "codex")
    assert from_elsewhere == from_root


def test_detection_leaves_the_probed_locations_untouched(probe: Path, tmp_path: Path) -> None:
    (probe / ".codex").mkdir()
    before = sorted(p.name for p in probe.iterdir())

    detect_available_harnesses()

    assert sorted(p.name for p in probe.iterdir()) == before
