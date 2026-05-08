"""Port of `tests/installer.test.ts`.

The TS suite spawns ``cheese install`` as a subprocess via ``tsx`` and asserts
on the formatted stdout/stderr. The Python ``cheese`` CLI does not exist yet
(arrives in US-015), so this port translates the test surface to library-level
calls against ``install_harnesses`` + ``format_install_report`` while still
asserting on the same formatted output strings the TS test verifies.

Each TS case maps 1:1 to a Python case:

* ``runCheeseInstall(["--project-root", projectRoot])`` →
  ``install_harnesses(project_root=..., environment=...)`` with a mocked
  ``find_command`` / ``has_directory`` / ``execute_command``.
* ``--harness foo,bar`` → ``requested_harnesses=[foo, bar]`` (the CLI parses
  the comma-list into the same shape).
* PATH overrides → ``find_command`` only resolves the names enumerated in the
  per-test environment.
* ``-H cursor,copilot-cli -H cursor`` → the dedupe happens in
  ``parse_harness_overrides``; the test uses that helper directly to mirror
  what the CLI will do in US-015.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from cheese_flow.lib.install_plan import parse_harness_overrides
from cheese_flow.lib.installer import (
    CommandExecutionResult,
    InstallEnvironment,
    InstallReport,
    format_install_report,
    install_harnesses,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def project_factory(tmp_path: Path) -> Any:
    """Returns a callable that copies agents/skills/commands into a fresh tmp dir."""

    created: list[Path] = []

    def make_project_root(prefix: str) -> Path:
        directory = tmp_path / f"{prefix}-{uuid.uuid4()}"
        directory.mkdir(parents=True)
        for source_name in ("agents", "skills", "commands"):
            shutil.copytree(REPO_ROOT / source_name, directory / source_name)
        created.append(directory)
        return directory

    yield make_project_root

    for directory in created:
        shutil.rmtree(directory, ignore_errors=True)


def _make_environment(
    *,
    commands: dict[str, str] | None = None,
    surfaces: list[str] | None = None,
    on_execute: Any = None,
) -> InstallEnvironment:
    command_map = dict(commands or {})
    surface_set = set(surfaces or [])

    async def find_command(command: str) -> str | None:
        return command_map.get(command)

    async def has_directory(directory_path: str) -> bool:
        return directory_path in surface_set

    async def execute_command(
        command: str, args: list[str], cwd: str
    ) -> CommandExecutionResult:
        if on_execute is not None:
            on_execute(command, args, cwd)
        return {"stdout": "", "stderr": ""}

    return InstallEnvironment(
        findCommand=find_command,
        hasDirectory=has_directory,
        executeCommand=execute_command,
    )


def test_fails_with_guidance_and_emits_no_bundles_when_auto_detect_finds_nothing(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-no-detect")

    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            environment=_make_environment(),
        )
    )

    assert report["ok"] is False
    output = format_install_report(report)
    assert "No installed harnesses detected" in output
    assert "cheese compile" in output
    assert not (project_root / ".claude").exists()
    assert not (project_root / ".codex").exists()
    assert not (project_root / ".copilot").exists()
    assert not (project_root / ".cursor").exists()


def test_auto_detects_cursor_and_copilot_compiles_only_those_bundles_and_installs_copilot(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-auto")
    (project_root / ".cursor").mkdir()

    captured: list[tuple[str, list[str], str]] = []

    def record(command: str, args: list[str], cwd: str) -> None:
        captured.append((command, args, cwd))

    environment = _make_environment(
        commands={"copilot": "/mock/bin/copilot"},
        surfaces=[str(project_root / ".cursor")],
        on_execute=record,
    )

    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            environment=environment,
        )
    )
    output = format_install_report(report)

    assert "[installed] Cursor" in output
    assert "[installed] GitHub Copilot CLI" in output
    assert "[skipped] Claude Code" in output
    assert "[skipped] Codex" in output
    assert (project_root / ".cursor").exists()
    assert (project_root / ".copilot").exists()
    assert not (project_root / ".claude").exists()
    assert not (project_root / ".codex").exists()
    assert any(
        command == "/mock/bin/copilot"
        and args == ["plugin", "install", str(project_root / ".copilot")]
        for command, args, _ in captured
    )


def test_auto_detects_claude_code_and_codex_from_path_and_reports_manual_next_steps(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-manual-auto")

    environment = _make_environment(
        commands={"claude": "/mock/bin/claude", "codex": "/mock/bin/codex"},
    )
    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            environment=environment,
        )
    )
    output = format_install_report(report)

    assert report["ok"] is False
    assert "[manual] Claude Code" in output
    assert "[manual] Codex" in output
    assert "[skipped] Cursor" in output
    assert "[skipped] GitHub Copilot CLI" in output
    assert (
        f"claude plugin marketplace add {json.dumps(str(project_root / '.claude'))}"
    ) in output
    assert (
        f"codex plugin marketplace add {json.dumps(str(project_root / '.codex'))}"
    ) in output
    assert (
        'Open Claude Code, run /plugin, then install "cheese-flow" from "cheese-flow-local".'
    ) in output
    assert "Restart Codex." in output
    assert "Guidance:" not in output
    assert (project_root / ".claude" / ".claude-plugin" / "marketplace.json").exists()
    assert (
        project_root / ".codex" / ".agents" / "plugins" / "marketplace.json"
    ).exists()


def test_marks_claude_code_and_codex_as_manual_and_emits_local_marketplace_helpers(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-manual")

    environment = _make_environment(
        commands={"claude": "/mock/bin/claude", "codex": "/mock/bin/codex"},
    )
    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            requested_harnesses=parse_harness_overrides(["claude-code,codex"]),
            environment=environment,
        )
    )
    output = format_install_report(report)

    assert report["ok"] is False
    assert "[manual] Claude Code" in output
    assert (
        f"claude plugin marketplace add {json.dumps(str(project_root / '.claude'))}"
    ) in output
    assert "[manual] Codex" in output
    assert (
        f"codex plugin marketplace add {json.dumps(str(project_root / '.codex'))}"
    ) in output
    assert "Restart Codex." in output
    assert 'Open /plugins, choose "cheese-flow-local"' in output

    claude_marketplace = json.loads(
        (project_root / ".claude" / ".claude-plugin" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    assert claude_marketplace["plugins"][0]["source"] == "./"

    codex_marketplace = json.loads(
        (
            project_root / ".codex" / ".agents" / "plugins" / "marketplace.json"
        ).read_text(encoding="utf-8")
    )
    assert codex_marketplace["plugins"][0]["source"] == {
        "source": "local",
        "path": "./",
    }


def test_parses_repeated_harness_overrides_and_bypasses_auto_detect_for_other_harnesses(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-explicit")
    (project_root / ".cursor").mkdir()

    captured: list[tuple[str, list[str], str]] = []

    def record(command: str, args: list[str], cwd: str) -> None:
        captured.append((command, args, cwd))

    environment = _make_environment(
        commands={
            "claude": "/mock/bin/claude",
            "codex": "/mock/bin/codex",
            "copilot": "/mock/bin/copilot",
        },
        on_execute=record,
    )
    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            requested_harnesses=parse_harness_overrides(
                ["cursor,copilot-cli", "cursor"]
            ),
            environment=environment,
        )
    )
    output = format_install_report(report)

    assert (
        len([line for line in output.split("\n") if "[installed] Cursor" in line]) == 1
    )
    assert "[installed] GitHub Copilot CLI" in output
    assert "[skipped] Claude Code" in output
    assert "[skipped] Codex" in output
    assert (project_root / ".cursor").exists()
    assert (project_root / ".copilot").exists()
    assert not (project_root / ".claude").exists()
    assert not (project_root / ".codex").exists()
    assert any(
        command == "/mock/bin/copilot"
        and args == ["plugin", "install", str(project_root / ".copilot")]
        for command, args, _ in captured
    )


def test_fails_a_selected_copilot_install_when_the_copilot_cli_is_unavailable(
    project_factory: Any,
) -> None:
    project_root = project_factory("install-copilot-missing")

    environment = _make_environment()
    report = asyncio.run(
        install_harnesses(
            project_root=str(project_root),
            requested_harnesses=parse_harness_overrides(["copilot-cli"]),
            environment=environment,
        )
    )
    output = format_install_report(report)

    assert report["ok"] is False
    assert "[failed] GitHub Copilot CLI" in output
    assert 'requires the "copilot" command on PATH' in output
    assert (project_root / ".copilot").exists()


def test_install_report_typed_dict_fields_match_ts_shape() -> None:
    """Sanity: TS ``InstallReport`` carries ``selectionMode``, ``results``,
    ``ok``, optional ``guidance``. The Python TypedDict mirror should accept the
    same payload shapes — verify by constructing a minimal report."""
    report: InstallReport = {
        "selectionMode": "auto-detect",
        "results": [],
        "ok": True,
    }
    assert report["selectionMode"] == "auto-detect"
    assert report["results"] == []
    assert report["ok"] is True
