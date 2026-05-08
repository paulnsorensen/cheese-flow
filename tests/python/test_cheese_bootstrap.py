"""Port of ``tests/cheese-bootstrap.test.ts`` — black-box tests for
``hooks/cheese-bootstrap.sh``.
"""

from __future__ import annotations

import os
import stat as stat_mod
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "hooks" / "cheese-bootstrap.sh"


def _run(cwd: Path, path_override: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path_override is not None:
        env["PATH"] = path_override
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _make_shim_dir(tmp_path: Path, body: str) -> Path:
    shim_dir = tmp_path / f"shim-{abs(hash(body))}"
    shim_dir.mkdir()
    shim = shim_dir / "cheese"
    shim.write_text(body, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return shim_dir


# ─── AC5: hooks/cheese-bootstrap.sh idempotent bootstrap ─────────────────────


def test_creates_cheese_dir_and_adds_dot_cheese_exactly_once_when_run_twice(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "twice"
    cwd.mkdir()
    (cwd / ".gitignore").write_text("node_modules/\ndist/\n", encoding="utf-8")

    first = _run(cwd)
    assert first.returncode == 0, f"first run stderr: {first.stderr}"
    second = _run(cwd)
    assert second.returncode == 0, f"second run stderr: {second.stderr}"

    assert (cwd / ".cheese").is_dir()
    gitignore = (cwd / ".gitignore").read_text(encoding="utf-8")
    matching = [line for line in gitignore.splitlines() if line == ".cheese/"]
    assert len(matching) == 1


def test_creates_gitignore_containing_dot_cheese_when_missing(tmp_path: Path) -> None:
    cwd = tmp_path / "missing"
    cwd.mkdir()

    result = _run(cwd)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (cwd / ".cheese").is_dir()

    gitignore = (cwd / ".gitignore").read_text(encoding="utf-8")
    matching = [line for line in gitignore.splitlines() if line == ".cheese/"]
    assert len(matching) == 1


def test_preserves_existing_entries_when_gitignore_lacks_trailing_newline(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "no-newline"
    cwd.mkdir()
    (cwd / ".gitignore").write_text("node_modules/\ndist/", encoding="utf-8")

    result = _run(cwd)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    lines = [line for line in (cwd / ".gitignore").read_text(encoding="utf-8").splitlines() if line]
    assert "node_modules/" in lines
    assert "dist/" in lines
    assert ".cheese/" in lines
    assert len([line for line in lines if line == ".cheese/"]) == 1


def test_writes_single_dot_cheese_line_when_gitignore_is_empty(tmp_path: Path) -> None:
    cwd = tmp_path / "empty"
    cwd.mkdir()
    (cwd / ".gitignore").write_text("", encoding="utf-8")

    result = _run(cwd)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (cwd / ".gitignore").read_text(encoding="utf-8") == ".cheese/\n"


def test_preserves_existing_contents_inside_pre_existing_cheese_dir(tmp_path: Path) -> None:
    cwd = tmp_path / "existing"
    cwd.mkdir()
    (cwd / ".cheese" / "specs").mkdir(parents=True)
    (cwd / ".cheese" / "specs" / "existing.md").write_text("preserve me", encoding="utf-8")

    result = _run(cwd)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    preserved = (cwd / ".cheese" / "specs" / "existing.md").read_text(encoding="utf-8")
    assert preserved == "preserve me"


def test_treats_dot_cheese_no_trailing_slash_as_distinct(tmp_path: Path) -> None:
    cwd = tmp_path / "no-slash"
    cwd.mkdir()
    (cwd / ".gitignore").write_text(".cheese\n", encoding="utf-8")

    result = _run(cwd)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    lines = [line for line in (cwd / ".gitignore").read_text(encoding="utf-8").splitlines() if line]
    assert lines == [".cheese", ".cheese/"]


# ─── hooks/cheese-bootstrap.sh — CLI handoff (R5) ────────────────────────────


def test_exits_zero_when_cheese_is_not_on_path(tmp_path: Path) -> None:
    cwd = tmp_path / "no-cheese"
    cwd.mkdir()
    empty = tmp_path / "empty-path"
    empty.mkdir()

    result = _run(cwd, f"{empty}:/usr/bin:/bin")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (cwd / ".cheese").is_dir()


def test_invokes_session_start_when_present_and_continues_on_nonzero_exit(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "shim-7"
    cwd.mkdir()
    call_log = cwd / "cheese-call.log"
    shim_dir = _make_shim_dir(
        tmp_path,
        f'#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > {call_log!s}\nexit 7\n',
    )
    new_path = f"{shim_dir}:{os.environ.get('PATH', '')}"

    result = _run(cwd, new_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    recorded = call_log.read_text(encoding="utf-8")
    assert "session-start" in recorded
    assert "--quiet" in recorded
    assert "--max-time" in recorded


def test_invokes_session_start_with_root_pointing_at_worktree(tmp_path: Path) -> None:
    cwd = tmp_path / "shim-0"
    cwd.mkdir()
    call_log = cwd / "cheese-call.log"
    shim_dir = _make_shim_dir(
        tmp_path,
        f'#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > {call_log!s}\nexit 0\n',
    )
    new_path = f"{shim_dir}:{os.environ.get('PATH', '')}"

    result = _run(cwd, new_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    recorded = call_log.read_text(encoding="utf-8")
    assert "--root" in recorded
    real_cwd = str(cwd.resolve())
    assert str(cwd) in recorded or real_cwd in recorded
