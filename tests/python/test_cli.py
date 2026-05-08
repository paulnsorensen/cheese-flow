"""Tests for the Typer ``cheese`` CLI surface (``cheese_flow.cli``).

Replaces the TS Commander coverage from the integration ``--help`` smoke
tests in ``tests/mcp-proxy.test.ts`` and ``tests/milknado.test.ts``. Per
US-015, the surface is the same seven subcommands plus selected milknado
top-level aliases.
"""

from __future__ import annotations

from cheese_flow.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_root_help_lists_all_seven_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.stdout
    for command in (
        "compile",
        "install",
        "doctor",
        "lint",
        "milknado",
        "session-start",
        "mcp",
    ):
        assert command in output, f"missing subcommand in --help: {command!r}\n{output}"


def test_root_help_lists_milknado_top_level_alias() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "solve-blend" in result.stdout


def test_mcp_help_mentions_project_root_option() -> None:
    """Mirrors ``mcp-proxy.test.ts`` "wires up the mcp help" smoke."""
    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.stdout
    assert "Usage:" in result.stdout
    assert "project-root" in result.stdout.lower()


def test_milknado_help_mentions_project_root() -> None:
    """Mirrors ``milknado.test.ts`` "wires up milknado help" smoke."""
    import os

    env = {**os.environ, "TERMINAL_WIDTH": "200", "COLUMNS": "200"}
    result = runner.invoke(app, ["milknado", "--help"], env=env)
    assert result.exit_code == 0
    assert "milknado" in result.stdout
    assert "Usage:" in result.stdout
    assert "project-root" in result.stdout.lower()


def test_doctor_help_describes_purpose() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "Verify required" in result.stdout


def test_compile_help_documents_harness_flag() -> None:
    result = runner.invoke(app, ["compile", "--help"])
    assert result.exit_code == 0
    assert "-H" in result.stdout
    assert "--harness" in result.stdout


def test_install_help_documents_harness_flag() -> None:
    result = runner.invoke(app, ["install", "--help"])
    assert result.exit_code == 0
    assert "-H" in result.stdout
    assert "--harness" in result.stdout


def test_lint_help_documents_project_root() -> None:
    result = runner.invoke(app, ["lint", "--help"])
    assert result.exit_code == 0
    assert "project-root" in result.stdout.lower()


def test_session_start_help_documents_options() -> None:
    result = runner.invoke(app, ["session-start", "--help"])
    assert result.exit_code == 0
    assert "--root" in result.stdout
    assert "--quiet" in result.stdout
    assert "--max-time" in result.stdout


def test_solve_blend_help_describes_alias() -> None:
    result = runner.invoke(app, ["solve-blend", "--help"])
    assert result.exit_code == 0
    assert "blend" in result.stdout.lower()
