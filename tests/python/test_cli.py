"""Tests for the Typer ``cheese`` CLI surface (``cheese_flow.cli``).

The v1 surface is exactly two commands: ``install`` and ``doctor``.
"""

from __future__ import annotations

from cheese_flow.cli import app
from typer.testing import CliRunner

# Help-text assertions below rely on Typer's plain (Click) help formatter, which
# renders option names deterministically regardless of terminal width. The
# session conftest sets ``TYPER_USE_RICH=0`` before typer is imported; with Rich
# enabled, headless CI panels render with no body text and these assertions fail.
runner = CliRunner()

REMOVED_COMMANDS = (
    "compile",
    "lint",
    "milknado",
    "session-start",
    "mcp",
    "solve-blend",
)


def test_root_help_lists_exactly_install_and_doctor() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.stdout
    assert "install" in output
    assert "doctor" in output


def test_root_help_omits_the_purged_v0_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in REMOVED_COMMANDS:
        assert command not in result.stdout, f"purged command still exposed: {command!r}"


def test_purged_commands_are_rejected() -> None:
    for command in REMOVED_COMMANDS:
        result = runner.invoke(app, [command])
        assert result.exit_code != 0, f"purged command still runs: {command!r}"


def test_install_help_documents_its_three_options() -> None:
    result = runner.invoke(app, ["install", "--help"])
    assert result.exit_code == 0
    output = result.stdout
    assert "--config" in output
    assert "--dry-run" in output
    assert "--json" in output


def test_doctor_help_documents_config_option() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.stdout


def test_doctor_help_omits_install_only_options() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" not in result.stdout
    assert "--json" not in result.stdout
