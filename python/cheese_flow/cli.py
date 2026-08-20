"""Cyclopts CLI entry point for cheese-flow.

``cheese install`` runs the wizard, or installs headlessly from a manifest
(``--config``) or from options (``--harness``/``--component``/``--repo``).
``cheese doctor`` verifies declared managed state.

Output discipline: in headless mode stdout carries exactly one JSON document and
nothing else. Every prompt, progress line, and diagnostic goes to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

from cyclopts import App, Group, Parameter
from rich.console import Console

from cheese_flow.adapters import default_component_adapters
from cheese_flow.desired_state import (
    ManifestError,
    OptionError,
    default_config_path,
    load_desired_state,
    save_desired_state,
    state_from_options,
)
from cheese_flow.doctor import verify_desired_state
from cheese_flow.install import apply_install_plan, build_install_plan
from cheese_flow.models import (
    COMPONENT_NAMES,
    ApplyReport,
    CommandRunner,
    DesiredState,
    DoctorReport,
    InstallPlan,
    ReportStatus,
)
from cheese_flow.profiles.cli import app as profile_app
from cheese_flow.runner import DEFAULT_TIMEOUT_SECONDS, SubprocessRunner
from cheese_flow.tui import run_wizard

_MANIFEST_EXIT_CODE = 2
_FAILURE_EXIT_CODE = 1

# git has no read timeout of its own; every child clone must abort a stalled
# transfer instead of hanging forever. bootstrap.sh sets the same bound for the
# uvx clone it execs directly, which this runner cannot reach.
_GIT_LOW_SPEED_DEFAULTS = {"GIT_HTTP_LOW_SPEED_LIMIT": "1000", "GIT_HTTP_LOW_SPEED_TIME": "30"}

app = App(
    name="cheese",
    version=version("cheese-flow"),
    help="Install and verify the cheese ecosystem across Claude Code, Codex, and Cursor.",
)

app.command(profile_app)

_STATE_SOURCE = Group("State source (choose the wizard, a manifest, or options)")
_BEHAVIOR = Group("Behavior")


@app.command
def install(
    *,
    config: Annotated[
        Path | None,
        Parameter(
            group=_STATE_SOURCE,
            help="Apply this manifest headlessly instead of running the wizard.",
        ),
    ] = None,
    harness: Annotated[
        list[str] | None,
        Parameter(
            group=_STATE_SOURCE,
            negative="",
            help="Harnesses to manage, comma- or space-separated. Repeatable. Runs headlessly.",
        ),
    ] = None,
    component: Annotated[
        list[str] | None,
        Parameter(
            group=_STATE_SOURCE,
            negative="",
            help="Components to install, comma- or space-separated. Defaults to all of them.",
        ),
    ] = None,
    repo: Annotated[
        list[str] | None,
        Parameter(
            group=_STATE_SOURCE,
            negative="",
            help="Repositories to index, comma- or space-separated. Relative paths are resolved.",
        ),
    ] = None,
    write_config: Annotated[
        bool,
        Parameter(
            group=_BEHAVIOR,
            negative="",
            help="Persist the resolved manifest. Options are ephemeral without it.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(
            group=_BEHAVIOR,
            negative="",
            help="Emit the plan without changing managed state.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        Parameter(
            name="--json",
            group=_BEHAVIOR,
            negative="",
            help="Write one JSON document to stdout.",
        ),
    ] = False,
    timeout: Annotated[
        float,
        Parameter(
            group=_BEHAVIOR,
            help="Seconds a single command may run before it is killed.",
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Install the selected components for the selected harnesses and repositories."""
    console = _console()
    declared = (_tokens(harness), _tokens(component), _tokens(repo))
    _reject_conflicting_options(
        console, config=config, declared=declared, write_config=write_config, dry_run=dry_run
    )
    headless = config is not None or json_output or any(declared)
    if any(declared):
        state = _option_state(console, *declared)
    elif headless:
        state = _headless_state(console, config)
    else:
        state = _interactive_state(console, dry_run=dry_run)

    if dry_run:
        # spec:105 — resolve metadata against a throwaway npm cache, removed on exit.
        with tempfile.TemporaryDirectory(prefix="cheese-npm-cache-") as cache:
            runner = _default_runner({"npm_config_cache": cache}, timeout=timeout)
            with _resolution_failure_reported(console):
                plan = build_install_plan(state, default_component_adapters(runner))
        console.print("Dry run: emitting the plan without executing it.")
        _announce(console, plan)
        report = ApplyReport(status=ReportStatus.SUCCEEDED, manifest=state, plan=plan)
    else:
        runner = _default_runner(timeout=timeout)
        # One adapter set for planning and apply: apply must reuse the versions
        # planning resolved (acceptance:150).
        adapters = default_component_adapters(runner)
        with _resolution_failure_reported(console):
            plan = build_install_plan(state, adapters)
        if write_config or not headless:
            save_desired_state(state, default_config_path())
            console.print(f"Wrote {default_config_path()}")
        _announce(console, plan)
        report = apply_install_plan(plan, runner, adapters=adapters)

    _emit(console, report, headless=headless)


@app.command
def doctor(
    *,
    config: Annotated[
        Path | None,
        Parameter(help="Manifest to verify. Defaults to the standard path."),
    ] = None,
    timeout: Annotated[
        float,
        Parameter(help="Seconds a single command may run before it is killed."),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Verify declared managed state without changing it."""
    console = _console()
    state = _headless_state(console, config)
    runner = _default_runner(timeout=timeout)
    adapters = default_component_adapters(runner)
    console.print("Verifying declared managed state.")
    with _resolution_failure_reported(console):
        report = verify_desired_state(state, adapters, runner)
    _emit(console, report, headless=True)


@contextmanager
def _resolution_failure_reported(console: Console) -> Iterator[None]:
    """Report a version-resolution failure as a diagnostic, not a traceback.

    Adapters raise RuntimeError while planning when ``npm view`` cannot answer —
    npm missing on a bare host, or no route to the registry. Nothing has been
    planned or mutated yet, so this fails like an invalid manifest does: one
    message on stderr, nothing on stdout, and a nonzero exit.
    """
    try:
        yield
    except RuntimeError as error:
        console.print(f"Planning failed: {error}")
        raise SystemExit(_FAILURE_EXIT_CODE) from error


def _console() -> Console:
    """A console bound to stderr — stdout belongs to the JSON document alone."""
    return Console(stderr=True, markup=False, highlight=False, soft_wrap=True)


def _default_runner(
    env: Mapping[str, str] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CommandRunner:
    # Only fill in a default when the caller hasn't exported a non-empty value —
    # SubprocessRunner overlays ``env`` on top of ``os.environ``, so a plain
    # unconditional default would override a caller-set value.
    overlay = {
        key: value for key, value in _GIT_LOW_SPEED_DEFAULTS.items() if not os.environ.get(key)
    }
    overlay.update(env or {})
    return SubprocessRunner(env=overlay, timeout=timeout)


def _tokens(values: list[str] | None) -> tuple[str, ...]:
    """Split option values on commas or whitespace, so both separators read alike."""
    return tuple(token for value in values or () for token in value.replace(",", " ").split())


def _reject_conflicting_options(
    console: Console,
    *,
    config: Path | None,
    declared: tuple[tuple[str, ...], ...],
    write_config: bool,
    dry_run: bool,
) -> None:
    """Refuse option sets that name two sources of state, or a write that cannot happen."""
    if config is not None and any(declared):
        console.print(
            "Invalid options: --config and --harness/--component/--repo "
            "name two sources of desired state."
        )
        raise SystemExit(_MANIFEST_EXIT_CODE)
    if write_config and dry_run:
        console.print(
            "Invalid options: --dry-run persists nothing, so --write-config cannot apply."
        )
        raise SystemExit(_MANIFEST_EXIT_CODE)


def _option_state(
    console: Console,
    harnesses: tuple[str, ...],
    components: tuple[str, ...],
    repositories: tuple[str, ...],
) -> DesiredState:
    """Build the desired state from options, failing before planning or mutation."""
    try:
        return state_from_options(
            harnesses,
            components or COMPONENT_NAMES,
            tuple(Path(path) for path in repositories),
        )
    except OptionError as error:
        console.print(f"Invalid options: {error}")
        raise SystemExit(_MANIFEST_EXIT_CODE) from error


def _headless_state(console: Console, config: Path | None) -> DesiredState:
    """Load the manifest, failing before planning, resolution, or mutation."""
    path = config if config is not None else default_config_path()
    try:
        return load_desired_state(path)
    except ManifestError as error:
        console.print(f"Invalid manifest: {error}")
        raise SystemExit(_MANIFEST_EXIT_CODE) from error


def _has_terminal() -> bool:
    """Whether stdin can carry wizard answers — the one environment probe here."""
    return sys.stdin.isatty()


def _interactive_state(console: Console, *, dry_run: bool) -> DesiredState:
    # The wizard reads stdin a line at a time. Without a terminal the first read
    # returns EOF, which the wizard cannot distinguish from a user quitting, so
    # the run would report "Cancelled" and hide the real problem: nobody could
    # have answered. Fail here instead, where the options that avoid the wizard
    # are still worth naming. bootstrap.sh reconnects /dev/tty for the
    # curl-pipe-sh case, so reaching this means no terminal exists at all.
    if not _has_terminal():
        console.print(
            "No terminal available for the wizard. Pass --harness/--component "
            "to install headlessly, or --config <manifest> to apply a saved one."
        )
        raise SystemExit(_FAILURE_EXIT_CODE)
    state = run_wizard(_prefill(console))
    if state is None:
        console.print("Cancelled: no manifest was written and nothing was installed.")
        raise SystemExit(_FAILURE_EXIT_CODE)
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
        raise SystemExit(_FAILURE_EXIT_CODE)


def _render(console: Console, report: ApplyReport | DoctorReport) -> None:
    console.print(f"Status: {report.status.value}")
    for result in report.results:
        console.print(f"  {result.status.value:<11} {result.step_id}")
        if result.remediation:
            console.print(f"    {result.remediation}")


if __name__ == "__main__":
    app()
