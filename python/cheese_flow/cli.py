"""Typer CLI entry point for cheese-flow.

``cheese install`` runs the wizard, or applies a manifest headlessly with
``--config``. ``cheese doctor`` verifies declared managed state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="cheese",
    help="Install and verify the cheese ecosystem across Claude Code, Codex, and Cursor.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def install(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Apply this manifest headlessly instead of running the wizard.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Emit the plan without changing managed state."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Write one JSON document to stdout."),
    ] = False,
) -> None:
    """Install the selected components for the selected harnesses and repositories."""
    raise NotImplementedError


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Manifest to verify. Defaults to the standard path."),
    ] = None,
) -> None:
    """Verify declared managed state without changing it."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
