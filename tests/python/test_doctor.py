"""Tests for `python/cheese_flow/lib/doctor.py`.

`src/lib/doctor.ts` shipped without a matching `tests/doctor.test.ts`,
so there were no vitest cases to port verbatim. These tests exercise
the ported surface (`TOOL_CHECKS`, `run_tool_check`,
`run_all_tool_checks`, `format_report`, `has_blocking_failure`) the way
the TS suite would have, using a tmp_path executable for the
subprocess-success case so we don't depend on whichever real binaries
happen to be on the developer's PATH.
"""

from __future__ import annotations

import asyncio
import stat
import textwrap
from pathlib import Path

import pytest
from cheese_flow.lib.doctor import (
    TOOL_CHECKS,
    ToolCheck,
    ToolResult,
    format_report,
    has_blocking_failure,
    run_all_tool_checks,
    run_tool_check,
)


def _make_executable(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def test_tool_checks_cover_required_recommended_and_suggested_tiers() -> None:
    by_name = {check.name: check for check in TOOL_CHECKS}
    assert by_name["tilth"].tier == "required"
    assert by_name["mergiraf"].tier == "recommended"
    assert by_name["rtk"].tier == "suggested"
    assert {check.tier for check in TOOL_CHECKS} == {
        "required",
        "recommended",
        "suggested",
    }
    for check in TOOL_CHECKS:
        assert check.purpose
        assert check.installHint


def _result(
    *,
    name: str = "tilth",
    tier: str = "required",
    ok: bool = True,
    version: str | None = None,
    error: str | None = None,
) -> ToolResult:
    return ToolResult(
        name=name,
        tier=tier,  # type: ignore[arg-type]
        purpose=f"{name} purpose",
        installHint=f"install {name}",
        ok=ok,
        version=version,
        error=error,
    )


def test_format_report_renders_ok_results_with_version_and_purpose() -> None:
    results = [_result(ok=True, version="tilth 1.2.3")]
    report = format_report(results)
    assert "cheese doctor — tool dependency check" in report
    assert "[REQUIRED] tilth: ok" in report
    assert "  tilth purpose" in report
    assert "  found: tilth 1.2.3" in report


def test_format_report_renders_ok_results_without_version_as_found() -> None:
    results = [_result(ok=True, version=None)]
    report = format_report(results)
    assert "[REQUIRED] tilth: ok" in report
    assert "  found" in report
    assert "  found:" not in report


def test_format_report_renders_missing_results_with_install_hint() -> None:
    results = [
        _result(name="mergiraf", tier="recommended", ok=False),
    ]
    report = format_report(results)
    assert "[RECOMMENDED] mergiraf: missing" in report
    assert "  install: install mergiraf" in report


def test_has_blocking_failure_is_true_only_for_missing_required_tools() -> None:
    assert has_blocking_failure([_result(tier="required", ok=False)]) is True
    assert has_blocking_failure([_result(tier="required", ok=True)]) is False
    assert has_blocking_failure([_result(name="rtk", tier="suggested", ok=False)]) is False
    assert has_blocking_failure([_result(name="mergiraf", tier="recommended", ok=False)]) is False


def test_run_tool_check_returns_version_for_real_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "bin"
    _make_executable(
        bin_dir,
        "fakery",
        textwrap.dedent(
            """\
            #!/bin/sh
            echo 'fakery 9.9.9'
            """
        ),
    )
    monkeypatch.setenv("PATH", str(bin_dir))
    check = ToolCheck(
        name="fakery",
        tier="required",
        purpose="fake tool",
        installHint="brew install fakery",
    )
    result = asyncio.run(run_tool_check(check))
    assert result.ok is True
    assert result.version == "fakery 9.9.9"
    assert result.error is None
    assert result.name == "fakery"
    assert result.tier == "required"


def test_run_tool_check_marks_missing_when_executable_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))
    check = ToolCheck(
        name="definitely-not-a-real-binary-xyz",
        tier="required",
        purpose="...",
        installHint="...",
    )
    result = asyncio.run(run_tool_check(check))
    assert result.ok is False
    assert result.version is None
    assert result.error is not None and result.error != ""


def test_run_tool_check_marks_failure_when_executable_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "bin"
    _make_executable(
        bin_dir,
        "grump",
        textwrap.dedent(
            """\
            #!/bin/sh
            exit 7
            """
        ),
    )
    monkeypatch.setenv("PATH", str(bin_dir))
    check = ToolCheck(
        name="grump",
        tier="required",
        purpose="grumpy",
        installHint="install grump",
    )
    result = asyncio.run(run_tool_check(check))
    assert result.ok is False
    assert result.error == "exited with code 7"
    assert result.version is None


def test_run_tool_check_marks_ok_without_version_when_stdout_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "bin"
    _make_executable(
        bin_dir,
        "silent",
        textwrap.dedent(
            """\
            #!/bin/sh
            exit 0
            """
        ),
    )
    monkeypatch.setenv("PATH", str(bin_dir))
    check = ToolCheck(
        name="silent",
        tier="required",
        purpose="silent",
        installHint="install silent",
    )
    result = asyncio.run(run_tool_check(check))
    assert result.ok is True
    assert result.version is None


def test_run_all_tool_checks_returns_one_result_per_tool_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))
    results = asyncio.run(run_all_tool_checks())
    assert len(results) == len(TOOL_CHECKS)
    assert [r.name for r in results] == [c.name for c in TOOL_CHECKS]
