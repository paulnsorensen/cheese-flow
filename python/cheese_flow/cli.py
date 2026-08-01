"""Typer CLI entry point for cheese-flow.

``cheese install`` runs the wizard, or applies a manifest headlessly with
``--config``. ``cheese doctor`` verifies declared managed state.

Output discipline: in headless mode stdout carries exactly one JSON document and
nothing else. Every prompt, progress line, and diagnostic goes to stderr.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from cheese_flow.adapters import default_component_adapters
from cheese_flow.desired_state import (
    ManifestError,
    default_config_path,
    load_desired_state,
    save_desired_state,
)
from cheese_flow.doctor import verify_desired_state
from cheese_flow.install import apply_install_plan, build_install_plan
from cheese_flow.models import (
    ApplyReport,
    CommandRunner,
    DesiredState,
    DoctorReport,
    InstallPlan,
    ReportStatus,
)
from cheese_flow.runner import DEFAULT_TIMEOUT_SECONDS, SubprocessRunner
from cheese_flow.tui import run_wizard

_MANIFEST_EXIT_CODE = 2
_FAILURE_EXIT_CODE = 1

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
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Seconds a single command may run before it is killed.",
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Install the selected components for the selected harnesses and repositories."""
    console = _console()
    headless = config is not None or json_output
    state = (
        _headless_state(console, config)
        if headless
        else _interactive_state(console, dry_run=dry_run)
    )

    if dry_run:
        # spec:105 — resolve metadata against a throwaway npm cache, removed on exit.
        with tempfile.TemporaryDirectory(prefix="cheese-npm-cache-") as cache:
            runner = _default_runner({"npm_config_cache": cache}, timeout=timeout)
            plan = build_install_plan(state, default_component_adapters(runner))
        console.print("Dry run: emitting the plan without executing it.")
        _announce(console, plan)
        report = ApplyReport(status=ReportStatus.SUCCEEDED, manifest=state, plan=plan)
    else:
        runner = _default_runner(timeout=timeout)
        # One adapter set for planning and apply: apply must reuse the versions
        # planning resolved (acceptance:150).
        adapters = default_component_adapters(runner)
        plan = build_install_plan(state, adapters)
        if not headless:
            save_desired_state(state, default_config_path())
            console.print(f"Wrote {default_config_path()}")
        _announce(console, plan)
        report = apply_install_plan(plan, runner, adapters=adapters)

    _emit(console, report, headless=headless)


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Manifest to verify. Defaults to the standard path."),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Seconds a single command may run before it is killed.",
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Verify declared managed state without changing it."""
    console = _console()
    state = _headless_state(console, config)
    runner = _default_runner(timeout=timeout)
    adapters = default_component_adapters(runner)
    console.print("Verifying declared managed state.")
    report = verify_desired_state(state, adapters, runner)
    _emit(console, report, headless=True)


def _console() -> Console:
    """A console bound to stderr — stdout belongs to the JSON document alone."""
    return Console(stderr=True, markup=False, highlight=False, soft_wrap=True)


def _default_runner(
    env: Mapping[str, str] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CommandRunner:
    return SubprocessRunner(env=env, timeout=timeout)


def _headless_state(console: Console, config: Path | None) -> DesiredState:
    """Load the manifest, failing before planning, resolution, or mutation."""
    path = config if config is not None else default_config_path()
    try:
        return load_desired_state(path)
    except ManifestError as error:
        console.print(f"Invalid manifest: {error}")
        raise typer.Exit(_MANIFEST_EXIT_CODE) from error


def _interactive_state(console: Console, *, dry_run: bool) -> DesiredState:
    state = run_wizard(_prefill(console))
    if state is None:
        console.print("Cancelled: no manifest was written and nothing was installed.")
        raise typer.Exit(_FAILURE_EXIT_CODE)
    if dry_run:
        console.print("Dry run: the accepted state will not be persisted.")
    return state


def _prefill(console: Console) -> DesiredState | None:
    """Load the default manifest to prefill every wizard screen, if one exists."""
    path = default_config_path()
    if not path.exists():
        return None
    return _headless_state(console, path)


def _announce(console: Console, plan: InstallPlan) -> None:
    for step in plan.steps:
        target = step.harness or step.repository or ""
        console.print(f"  {step.step_id} [{step.component}] {target}".rstrip())


def _emit(console: Console, report: ApplyReport | DoctorReport, *, headless: bool) -> None:
    if headless:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        _render(console, report)
    if report.status is not ReportStatus.SUCCEEDED:
        raise typer.Exit(_FAILURE_EXIT_CODE)


def _render(console: Console, report: ApplyReport | DoctorReport) -> None:
    console.print(f"Status: {report.status.value}")
    for result in report.results:
        console.print(f"  {result.status.value:<11} {result.step_id}")
        if result.remediation:
            console.print(f"    {result.remediation}")


if __name__ == "__main__":
    app()
