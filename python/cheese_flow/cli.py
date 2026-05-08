"""Typer CLI entry point for cheese-flow.

Mirrors the TS Commander surface from ``src/index.ts``: ``compile``, ``install``,
``doctor``, ``lint``, ``milknado``, ``session-start``, ``mcp``. Top-level
aliases for selected milknado commands are wired through the same Typer app
(``cheese solve-blend`` runs the milknado blend demo TUI directly).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Annotated

import typer

from cheese_flow.adapters import HARNESS_NAMES
from cheese_flow.lib.compiler import compile_harness_bundles
from cheese_flow.lib.doctor import format_report, has_blocking_failure, run_all_tool_checks
from cheese_flow.lib.harness import HarnessName
from cheese_flow.lib.install_plan import dedupe_harness_names, parse_harness_overrides
from cheese_flow.lib.installer import (
    format_install_report,
    has_blocking_install_result,
    install_harnesses,
)
from cheese_flow.lib.lint_skills import format_lint_report, has_errors, lint_skills_directory
from cheese_flow.lib.session_start import RunSessionStartOptions, run_session_start

DEFAULT_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])

app = typer.Typer(
    name="cheese",
    help=(
        "Emit and locally install portable agents and Agent Skills as "
        "harness-specific markdown bundles."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _resolve_targets(harness: list[str] | None) -> list[HarnessName]:
    if not harness:
        return list(HARNESS_NAMES)
    return dedupe_harness_names(parse_harness_overrides(harness))


def _split_harness(values: list[str] | None) -> list[str]:
    """Commander accepts ``-H a,b`` and repeated ``-H``; mirror that."""
    if not values:
        return []
    out: list[str] = []
    for v in values:
        out.extend(part.strip() for part in v.split(",") if part.strip())
    return out


@app.command()
def compile(
    harness: Annotated[
        list[str] | None,
        typer.Option(
            "-H",
            "--harness",
            help="Harness target(s) to emit. Defaults to all supported harnesses.",
        ),
    ] = None,
    project_root: Annotated[
        str,
        typer.Option(
            "--project-root",
            help="Project root that contains ./agents and ./skills.",
        ),
    ] = DEFAULT_PROJECT_ROOT,
) -> None:
    """Emit one or more harness bundles from the repository sources."""
    targets = _resolve_targets(_split_harness(harness))
    outputs = asyncio.run(
        compile_harness_bundles(
            project_root=str(Path(project_root).resolve()),
            harnesses=targets,
        )
    )
    for output in outputs:
        typer.echo(f"Compiled harness bundle: {output}")


@app.command()
def install(
    harness: Annotated[
        list[str] | None,
        typer.Option(
            "-H",
            "--harness",
            help="Harness target(s) to install for. Defaults to auto-detect.",
        ),
    ] = None,
    project_root: Annotated[
        str,
        typer.Option(
            "--project-root",
            help="Project root that contains ./agents and ./skills.",
        ),
    ] = DEFAULT_PROJECT_ROOT,
) -> None:
    """Compile and install harness bundles into the local workspace."""
    requested = dedupe_harness_names(parse_harness_overrides(_split_harness(harness)))
    report = asyncio.run(
        install_harnesses(
            project_root=str(Path(project_root).resolve()),
            requested_harnesses=requested,
        )
    )
    typer.echo(format_install_report(report), nl=False)
    if has_blocking_install_result(report):
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Verify required, recommended, and suggested CLI tools are installed."""
    results = asyncio.run(run_all_tool_checks())
    typer.echo(format_report(results), nl=False)
    if has_blocking_failure(results):
        raise typer.Exit(code=1)


@app.command()
def lint(
    project_root: Annotated[
        str,
        typer.Option(
            "--project-root",
            help="Project root that contains ./skills.",
        ),
    ] = DEFAULT_PROJECT_ROOT,
) -> None:
    """Lint skills/ against the Agent Skills format (https://agentskills.io)."""
    skills_dir = Path(project_root).resolve() / "skills"
    report = asyncio.run(lint_skills_directory(str(skills_dir)))
    typer.echo(format_lint_report(report), nl=False)
    if has_errors(report):
        raise typer.Exit(code=1)


def _run_milknado(project_root: str) -> None:
    from blend_demo import render_tui, solve_blend_plan
    from rich.console import Console

    del project_root  # accepted for parity with TS surface; blend demo is in-process
    render_tui(solve_blend_plan(), Console())


@app.command()
def milknado(
    project_root: Annotated[
        str,
        typer.Option(
            "--project-root",
            help="Project root that contains ./python and pyproject.toml.",
        ),
    ] = DEFAULT_PROJECT_ROOT,
) -> None:
    """Run the sample Python backend and print its TUI."""
    _run_milknado(str(Path(project_root).resolve()))


@app.command(name="solve-blend")
def solve_blend() -> None:
    """Top-level alias: run the milknado blend-demo TUI."""
    _run_milknado(DEFAULT_PROJECT_ROOT)


@app.command(name="session-start")
def session_start(
    root: Annotated[str, typer.Option("--root", help="project root")] = ".",
    quiet: Annotated[bool, typer.Option("--quiet", help="suppress non-error output")] = False,
    max_time: Annotated[
        int,
        typer.Option("--max-time", help="soft budget for housekeeping (ms)"),
    ] = 5000,
) -> None:
    """Run cheese-flow housekeeping (sweep + update check) under a soft budget.

    Best-effort; never blocks session start.
    """
    # Best-effort: never block session start on housekeeping failure.
    with contextlib.suppress(Exception):
        asyncio.run(
            run_session_start(
                RunSessionStartOptions(
                    cwd=str(Path(root).resolve()),
                    maxTimeMs=max_time,
                    currentVersion="0.1.0",
                    quiet=quiet,
                )
            )
        )
    raise typer.Exit(code=0)


@app.command()
def mcp(
    project_root: Annotated[
        str,
        typer.Option(
            "--project-root",
            help="Project root that contains ./python/mcp_server.py and pyproject.toml.",
        ),
    ] = DEFAULT_PROJECT_ROOT,
) -> None:
    """Run the cheese-flow MCP server over stdio.

    Exposes both ``cheese_*`` and ``milknado_*`` prefixed tools from a single
    FastMCP instance.
    """
    del project_root  # accepted for parity with TS surface; server runs in-process
    from cheese_flow.mcp_server import run as run_mcp

    run_mcp()


if __name__ == "__main__":
    app()
