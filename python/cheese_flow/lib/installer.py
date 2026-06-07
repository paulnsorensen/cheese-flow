"""Port of `src/lib/installer.ts` — harness install orchestration.

Mirrors the TS surface: ``install_harnesses`` consumes ``install_plan``,
``harness_detection``, and (for the CLI capability tables it consults)
``harness_compat`` neighbours. Per-harness phase-1 actions:

* ``cursor`` — bundle root is the install surface; nothing else to do.
* ``copilot-cli`` — invoke ``copilot plugin install`` via ``execute_command``.
* ``claude-code`` — emit a Claude marketplace JSON; manual finish from CLI.
* ``codex`` — emit a Codex marketplace JSON; manual finish from CLI.

The TS module mocks ``execFile`` via the ``executeCommand`` field on the
detection environment; the Python port does the same with an ``execute_command``
async callable hung off ``InstallEnvironment``.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.compiler import CompiledHarnessBundle, compile_harness_bundle
from cheese_flow.lib.harness import HarnessName
from cheese_flow.lib.harness_detection import (
    HarnessDetectionEnvironment,
    find_command_on_path,
)
from cheese_flow.lib.install_plan import (
    HarnessInstallPlan,
    HarnessSelectionMode,
    create_harness_install_plan,
    dedupe_harness_names,
)
from cheese_flow.lib.local_marketplaces import (
    write_claude_marketplace,
    write_codex_marketplace,
)


class CommandExecutionResult(TypedDict):
    stdout: str
    stderr: str


CommandExecutor = Callable[[str, list[str], str], Awaitable[CommandExecutionResult]]


@dataclass(frozen=True)
class InstallEnvironment:
    """Override hooks for filesystem/PATH/exec probes (used by tests)."""

    findCommand: Callable[[str], Awaitable[str | None]] | None = None
    hasDirectory: Callable[[str], Awaitable[bool]] | None = None
    executeCommand: CommandExecutor | None = None


HarnessInstallState = Literal["installed", "manual", "skipped", "failed"]


class _HarnessInstallReportEntryRequired(TypedDict):
    harness: HarnessName
    displayName: str
    state: HarnessInstallState
    reason: str
    nextSteps: list[str]


class HarnessInstallReportEntry(_HarnessInstallReportEntryRequired, total=False):
    outputRoot: str


class _InstallReportRequired(TypedDict):
    selectionMode: HarnessSelectionMode
    results: list[HarnessInstallReportEntry]
    ok: bool


class InstallReport(_InstallReportRequired, total=False):
    guidance: str


class _Phase1InstallResult(TypedDict):
    state: Literal["installed", "manual", "failed"]
    reason: str
    nextSteps: list[str]


@dataclass(frozen=True)
class _SelectedInstallContext:
    bundle: CompiledHarnessBundle
    findCommand: Callable[[str], Awaitable[str | None]]
    executeCommand: CommandExecutor


def _shell_quote(value: str) -> str:
    return json.dumps(value)


def _error_message(error: BaseException) -> str:
    return str(error) if str(error) else type(error).__name__


def _command_failure_message(error: BaseException) -> str:
    stderr = getattr(error, "stderr", None)
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    if isinstance(stderr, str) and stderr.strip():
        return stderr.strip()

    stdout = getattr(error, "stdout", None)
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stdout, str) and stdout.strip():
        return stdout.strip()

    return _error_message(error)


async def default_command_executor(
    command: str, args: list[str], cwd: str
) -> CommandExecutionResult:
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if process.returncode != 0:
        error = RuntimeError(f"{command} {' '.join(args)} exited with code {process.returncode}")
        error.stdout = stdout  # type: ignore[attr-defined]
        error.stderr = stderr  # type: ignore[attr-defined]
        raise error
    return {"stdout": stdout, "stderr": stderr}


def _build_skipped_entry(
    project_root: str, harness: HarnessName, reason: str
) -> HarnessInstallReportEntry:
    adapter = HARNESS_ADAPTERS[harness]
    return {
        "harness": harness,
        "displayName": adapter.displayName,
        "state": "skipped",
        "reason": reason,
        "outputRoot": str(Path(project_root) / adapter.outputRoot),
        "nextSteps": [],
    }


def _build_selected_entry(
    bundle: CompiledHarnessBundle, result: _Phase1InstallResult
) -> HarnessInstallReportEntry:
    adapter = HARNESS_ADAPTERS[bundle.harness]
    return {
        "harness": bundle.harness,
        "displayName": adapter.displayName,
        "state": result["state"],
        "reason": result["reason"],
        "outputRoot": bundle.outputRoot,
        "nextSteps": result["nextSteps"],
    }


def _build_compile_failure_entry(
    project_root: str, harness: HarnessName, error: BaseException
) -> HarnessInstallReportEntry:
    adapter = HARNESS_ADAPTERS[harness]
    return {
        "harness": harness,
        "displayName": adapter.displayName,
        "state": "failed",
        "reason": f"Failed to compile {adapter.outputRoot}: {_error_message(error)}",
        "outputRoot": str(Path(project_root) / adapter.outputRoot),
        "nextSteps": [],
    }


async def _install_selected_harness(
    project_root: str,
    harness: HarnessName,
    *,
    find_command: Callable[[str], Awaitable[str | None]],
    execute_command: CommandExecutor,
) -> HarnessInstallReportEntry:
    try:
        bundle = await compile_harness_bundle(project_root=project_root, harness=harness)
    except Exception as error:  # noqa: BLE001
        return _build_compile_failure_entry(project_root, harness, error)

    context = _SelectedInstallContext(
        bundle=bundle,
        findCommand=find_command,
        executeCommand=execute_command,
    )
    result = await _run_phase1_install(context)
    return _build_selected_entry(bundle, result)


async def _install_selected_harnesses(
    plan: HarnessInstallPlan,
    *,
    project_root: str,
    environment: InstallEnvironment | None,
) -> dict[HarnessName, HarnessInstallReportEntry]:
    selected_entries: dict[HarnessName, HarnessInstallReportEntry] = {}
    find_command = (
        environment.findCommand
        if environment is not None and environment.findCommand is not None
        else find_command_on_path
    )
    execute_command = (
        environment.executeCommand
        if environment is not None and environment.executeCommand is not None
        else default_command_executor
    )

    for harness in plan["selectedHarnesses"]:
        selected_entries[harness] = await _install_selected_harness(
            project_root,
            harness,
            find_command=find_command,
            execute_command=execute_command,
        )

    return selected_entries


def _order_results(
    plan: HarnessInstallPlan,
    project_root: str,
    selected_entries: dict[HarnessName, HarnessInstallReportEntry],
) -> list[HarnessInstallReportEntry]:
    skipped_entries = [
        _build_skipped_entry(project_root, entry["harness"], entry["reason"])
        for entry in plan["entries"]
        if entry["selection"] == "skipped"
    ]
    selected_results = [
        selected_entries[harness]
        for harness in plan["selectedHarnesses"]
        if harness in selected_entries
    ]
    return [*selected_results, *skipped_entries]


def _is_successful(entry: HarnessInstallReportEntry) -> bool:
    return entry["state"] == "installed" or entry["state"] == "skipped"


async def install_harnesses(
    *,
    project_root: str,
    requested_harnesses: list[HarnessName] | None = None,
    environment: InstallEnvironment | None = None,
) -> InstallReport:
    requested = dedupe_harness_names(list(requested_harnesses or []))
    detection_env = (
        HarnessDetectionEnvironment(
            findCommand=environment.findCommand,
            hasDirectory=environment.hasDirectory,
        )
        if environment is not None
        else None
    )
    plan = await create_harness_install_plan(
        project_root=project_root,
        requested_harnesses=requested,
        environment=detection_env,
    )

    if not plan["ok"]:
        report: InstallReport = {
            "selectionMode": plan["selectionMode"],
            "results": [
                _build_skipped_entry(project_root, entry["harness"], entry["reason"])
                for entry in plan["entries"]
            ],
            "ok": False,
        }
        if "guidance" in plan:
            report["guidance"] = plan["guidance"]
        return report

    selected_entries = await _install_selected_harnesses(
        plan, project_root=project_root, environment=environment
    )
    results = _order_results(plan, project_root, selected_entries)
    return {
        "selectionMode": plan["selectionMode"],
        "results": results,
        "ok": all(_is_successful(entry) for entry in results),
    }


def has_blocking_install_result(report: InstallReport) -> bool:
    return not report["ok"]


def _format_entry(entry: HarnessInstallReportEntry) -> list[str]:
    lines = [f"[{entry['state']}] {entry['displayName']}"]
    if "outputRoot" in entry:
        lines.append(f"  Bundle: {entry['outputRoot']}")
    lines.append(f"  {entry['reason']}")
    if entry["nextSteps"]:
        lines.append("  Next steps:")
        lines.extend(f"  - {step}" for step in entry["nextSteps"])
    return lines


def format_install_report(report: InstallReport) -> str:
    lines: list[str] = []
    for entry in report["results"]:
        lines.extend(_format_entry(entry))
        lines.append("")
    if "guidance" in report:
        lines.append(f"Guidance: {report['guidance']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def _run_phase1_install(
    context: _SelectedInstallContext,
) -> _Phase1InstallResult:
    harness = context.bundle.harness
    if harness == "cursor":
        return await _install_cursor_bundle()
    if harness == "copilot-cli":
        return await _install_copilot_cli_bundle(context)
    if harness == "claude-code":
        return await _install_claude_code_bundle(context)
    if harness == "codex":
        return await _install_codex_bundle(context)
    raise ValueError(f"Unsupported harness: {harness}")  # pragma: no cover


async def _install_cursor_bundle() -> _Phase1InstallResult:
    return {
        "state": "installed",
        "reason": "Compiled .cursor/ tree is the installed surface for Cursor.",
        "nextSteps": [],
    }


async def _install_copilot_cli_bundle(
    context: _SelectedInstallContext,
) -> _Phase1InstallResult:
    copilot_path = await context.findCommand("copilot")
    install_command = f"copilot plugin install {_shell_quote(context.bundle.outputRoot)}"

    if copilot_path is None:
        return {
            "state": "failed",
            "reason": (
                'GitHub Copilot CLI requires the "copilot" command on PATH to finish installation.'
            ),
            "nextSteps": [f"Install GitHub Copilot CLI, then run {install_command}."],
        }

    try:
        await context.executeCommand(
            copilot_path,
            ["plugin", "install", context.bundle.outputRoot],
            os.path.dirname(context.bundle.outputRoot),
        )
    except Exception as error:  # noqa: BLE001
        return {
            "state": "failed",
            "reason": f"copilot plugin install failed: {_command_failure_message(error)}",
            "nextSteps": [],
        }

    return {
        "state": "installed",
        "reason": f"Installed the compiled bundle with {install_command}.",
        "nextSteps": [],
    }


async def _install_claude_code_bundle(
    context: _SelectedInstallContext,
) -> _Phase1InstallResult:
    details = await write_claude_marketplace(
        context.bundle.outputRoot,
        context.bundle.pluginMetadata,
    )
    claude_path = await context.findCommand("claude")
    add_command = f"claude plugin marketplace add {_shell_quote(context.bundle.outputRoot)}"
    reason = (
        'Claude Code still requires manual installation, and the "claude" CLI is not '
        "on PATH for the marketplace-add step."
        if claude_path is None
        else "Claude Code still requires manual installation after adding the local marketplace."
    )
    return {
        "state": "manual",
        "reason": reason,
        "nextSteps": [
            add_command,
            (
                f'Open Claude Code, run /plugin, then install "{details.pluginName}" '
                f'from "{details.marketplaceName}".'
            ),
        ],
    }


async def _install_codex_bundle(
    context: _SelectedInstallContext,
) -> _Phase1InstallResult:
    details = await write_codex_marketplace(
        context.bundle.outputRoot,
        context.bundle.pluginMetadata,
    )
    codex_path = await context.findCommand("codex")
    add_command = f"codex plugin marketplace add {_shell_quote(context.bundle.outputRoot)}"
    reason = (
        'Codex still requires manual installation, and the "codex" CLI is not on '
        "PATH for the marketplace-add step."
        if codex_path is None
        else "Codex still requires manual installation after adding the local marketplace."
    )
    return {
        "state": "manual",
        "reason": reason,
        "nextSteps": [
            add_command,
            "Restart Codex.",
            (
                f'Open /plugins, choose "{details.marketplaceName}", and install '
                f'"{details.pluginName}".'
            ),
        ],
    }


__all__ = [
    "CommandExecutionResult",
    "CommandExecutor",
    "HarnessInstallReportEntry",
    "HarnessInstallState",
    "InstallEnvironment",
    "InstallReport",
    "default_command_executor",
    "format_install_report",
    "has_blocking_install_result",
    "install_harnesses",
]
