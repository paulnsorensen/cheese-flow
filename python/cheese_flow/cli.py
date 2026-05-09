"""Placeholder Typer app for the `cheese` console script.

The real subcommand surface (`compile`, `install`, `doctor`, `lint`,
`milknado`, `session-start`, `mcp`) lands in US-015. Until then this app
exits zero so the entry point is wired but inert.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="cheese",
    help="cheese-flow CLI (placeholder; subcommands land in US-015).",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        return None
