"""Typer commands for the explicit cheese profile engine seams."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ValidationError

from .apply import apply_profile
from .compile import compile_profile
from .errors import ProfileError, ProfileLaunchError
from .isolation.runtime import remove_workspace
from .launch import _build_launch_with_workspace, _validate_exec_inputs
from .models import CompileRequest, LaunchRequest, LaunchSpec, ProjectPermissionsRequest
from .project_permissions import render_project_permissions
from .source import list_profiles, load_profile

app = typer.Typer(
    name="profile",
    help="Inspect, compile, apply, launch, and render agent profiles.",
    no_args_is_help=True,
    add_completion=False,
)

_FAILURE_EXIT_CODE = 1


def _environment() -> dict[str, str]:
    return dict(os.environ)


def _json_document(value: BaseModel | object) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, indent=2)


def _emit(value: BaseModel | object) -> None:
    typer.echo(_json_document(value))


def _handle(operation: Callable[[], object]) -> object:
    try:
        return operation()
    except (ProfileError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(_FAILURE_EXIT_CODE) from None


@app.command("list")
def list_command(
    source_root: Annotated[
        Path,
        typer.Option("--source-root", help="Explicit profile source root containing profiles/."),
    ],
) -> None:
    """List profiles beneath the explicit source root."""
    summaries = _handle(lambda: list_profiles(source_root))
    _emit([summary.model_dump(mode="json") for summary in summaries])


@app.command("describe")
def describe_command(
    name: Annotated[str, typer.Argument(help="Profile name to resolve.")],
    source_root: Annotated[
        Path,
        typer.Option("--source-root", help="Explicit profile source root containing profiles/."),
    ],
) -> None:
    """Show one fully resolved profile."""
    profile = _handle(lambda: load_profile(source_root, name, environment=_environment()))
    _emit(profile)


@app.command("compile")
def compile_command(
    name: Annotated[str, typer.Argument(help="Profile name to compile.")],
    source_root: Annotated[
        Path,
        typer.Option("--source-root", help="Explicit profile source root containing profiles/."),
    ],
    baseline: Annotated[
        Path, typer.Option("--baseline", help="Baseline tree used for drift and change capture.")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="Directory receiving the immutable publication.")
    ],
) -> None:
    """Compile a profile into an immutable manifest publication."""
    manifest = _handle(
        lambda: compile_profile(
            CompileRequest(
                profile_name=name,
                source_root=source_root,
                baseline_root=baseline,
                output_root=output,
            ),
            environment=_environment(),
        )
    )
    _emit(manifest)


@app.command("apply")
def apply_command(
    manifest: Annotated[Path, typer.Argument(help="Published manifest.json to apply.")],
    state: Annotated[
        Path | None,
        typer.Option("--state", help="Optional profile apply state path."),
    ] = None,
) -> None:
    """Apply one immutable profile manifest and reconcile prior ownership."""
    report = _handle(lambda: apply_profile(manifest, state_path=state))
    _emit(report)


def _exec_launch(spec: LaunchSpec) -> None:
    """Replace this process from one complete, validated launch specification."""
    if not isinstance(spec, LaunchSpec):
        raise ProfileLaunchError("launch exec requires a validated LaunchSpec")
    executable, argv, environment = _validate_exec_inputs(
        spec.executable,
        spec.argv,
        spec.environment,
    )
    exec_failed = False
    try:
        os.execvpe(executable, argv, environment)
    except (OSError, ValueError):
        exec_failed = True
    if exec_failed:
        raise ProfileLaunchError("could not exec harness")


def _safe_error_message(
    error: BaseException,
    environment: Mapping[str, str],
    workspace: Path | None = None,
) -> str:
    message = str(error) or type(error).__name__
    try:
        values = tuple(environment.values())
    except Exception:
        values = ()
    if workspace is not None:
        values += (str(workspace),)
    for value in values:
        if isinstance(value, str) and value:
            message = message.replace(value, "<redacted>")
    return message


def _cleanup_workspace(
    workspace: Path | None, *, environment: Mapping[str, str] | None = None
) -> str | None:
    if workspace is None:
        return None
    try:
        remove_workspace(workspace)
    except Exception as error:
        redaction_environment = environment if environment is not None else {}
        detail = _safe_error_message(error, redaction_environment, workspace)
        return f"workspace cleanup failed: {detail}"
    return None


@app.command(
    "launch",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def launch_command(
    context: typer.Context,
    harness: Annotated[str, typer.Argument(help="Harness to launch.")],
    name: Annotated[str, typer.Argument(help="Profile name to resolve.")],
    source_root: Annotated[
        Path,
        typer.Option("--source-root", help="Explicit profile source root containing profiles/."),
    ],
) -> None:
    """Resolve policy, then exec the harness with the complete LaunchSpec."""

    def execute() -> None:
        environment = _environment()
        request = LaunchRequest(
            profile_name=name,
            source_root=source_root,
            harness=harness,
            arguments=tuple(context.args),
        )
        spec: LaunchSpec | None = None
        workspace: Path | None = None
        try:
            spec, workspace = _build_launch_with_workspace(
                request,
                environment=environment,
            )
            _exec_launch(spec)
        except (OSError, ValueError):
            cleanup_environment: Mapping[str, str] = environment
            if spec is not None:
                cleanup_environment = {**environment, **spec.environment}
            cleanup_error = _cleanup_workspace(workspace, environment=cleanup_environment)
            message = f"could not exec harness {harness!r}"
            if cleanup_error is not None:
                message = f"{message}; {cleanup_error}"
            raise ProfileLaunchError(message) from None
        except ProfileError as error:
            cleanup_environment = environment
            if spec is not None:
                cleanup_environment = {**environment, **spec.environment}
            cleanup_error = _cleanup_workspace(workspace, environment=cleanup_environment)
            message = _safe_error_message(error, cleanup_environment, workspace)
            if cleanup_error is not None:
                message = f"{message}; {cleanup_error}"
            raise type(error)(message) from None

    _handle(execute)


@app.command("permissions")
def permissions_command(
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root", help="Explicit project root containing the permission fragment."
        ),
    ],
    local: Annotated[
        bool,
        typer.Option("--local", help="Write Claude's gitignored personal settings and skip Codex."),
    ] = False,
    harnesses: Annotated[
        list[str] | None,
        typer.Option("--harness", help="Harness to render; repeat for claude and codex."),
    ] = None,
) -> None:
    """Render project permissions from the fixed project-local fragment."""
    report = _handle(
        lambda: render_project_permissions(
            ProjectPermissionsRequest(
                project_root=project_root,
                local=local,
                harnesses=tuple(harnesses) if harnesses is not None else ("claude", "codex"),
            ),
            environment=_environment(),
        )
    )
    _emit(report)


__all__ = ["app"]
