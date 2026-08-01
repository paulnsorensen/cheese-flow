"""Deterministic planning and verified apply."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cheese_flow.models import (
    COMPONENT_NAMES,
    REDACTED,
    ApplyReport,
    CollisionClass,
    CommandOutcome,
    CommandRunner,
    ComponentAdapter,
    ComponentAdapters,
    ConfigEdit,
    ConfigEditSummary,
    DesiredState,
    InstallPlan,
    PlanStep,
    ReportStatus,
    RepositoryCandidate,
    StepResult,
    StepStatus,
    canonicalize,
    scan_argv,
)
from cheese_flow.repositories import discover_repositories
from cheese_flow.runner import SignalForwardingRunner

TAIL_LIMIT = 2000
"""Maximum number of characters kept from a command's stdout or stderr."""


def build_install_plan(state: DesiredState, adapters: ComponentAdapters) -> InstallPlan:
    """Collect every selected component's steps in canonical component order.

    Adapters resolve their versions once while planning, so the plan holds the
    exact argv Apply must run in this same run.
    """
    steps: list[PlanStep] = []
    for name in COMPONENT_NAMES:
        if name not in state.components:
            continue
        adapter = adapters.get(name)
        if adapter is None:
            raise ValueError(f"no adapter for selected component {name!r}")
        steps.extend(adapter.plan_steps(state))
    return InstallPlan(manifest=state, steps=tuple(steps))


def apply_install_plan(
    plan: InstallPlan, runner: CommandRunner, *, adapters: ComponentAdapters
) -> ApplyReport:
    """Run the plan, skipping steps whose postcondition already holds.

    A failed postcondition blocks dependent steps; unrelated components and
    repositories continue. There is no rollback.

    ``adapters`` must be the adapter instances the plan was built from, so
    postconditions verify the exact versions this run planned (acceptance:150).
    It is required: rebuilding adapters here would re-resolve every version and
    reject what the plan just installed.
    """
    results: list[StepResult] = []
    unmet: set[str] = set()
    repositories = _RepositoryRevalidation(plan)

    with _signal_scope(runner) as interruption:
        for index, step in enumerate(plan.steps):
            if interruption.signum is not None:
                results.extend(_not_started(remaining) for remaining in plan.steps[index:])
                break
            blocked = _blocking_reason(step, unmet, repositories)
            if blocked is not None:
                unmet.add(step.step_id)
                results.append(step_result(step, StepStatus.BLOCKED, remediation=blocked))
                continue
            result = _perform(step, adapters, runner, interruption)
            if result.status is not StepStatus.SKIPPED:
                repositories.note_mutation()
            if result.status not in (StepStatus.SUCCEEDED, StepStatus.SKIPPED):
                unmet.add(step.step_id)
            results.append(result)

    return ApplyReport(
        status=report_status(results),
        manifest=plan.manifest,
        plan=plan,
        results=tuple(results),
    )


def adapter_for(step: PlanStep, adapters: ComponentAdapters) -> ComponentAdapter:
    """Return the adapter that owns ``step``."""
    adapter = adapters.get(step.component)
    if adapter is None:
        raise ValueError(f"no adapter for component {step.component!r} (step {step.step_id!r})")
    return adapter


def report_status(results: Sequence[StepResult]) -> ReportStatus:
    """Fold step statuses into the run's overall status."""
    seen = {result.status for result in results}
    if StepStatus.INTERRUPTED in seen:
        return ReportStatus.INTERRUPTED
    if seen & {StepStatus.FAILED, StepStatus.BLOCKED}:
        return ReportStatus.FAILED
    return ReportStatus.SUCCEEDED


def apply_config_edit(edit: ConfigEdit) -> None:
    """Write ``edit.value`` at ``edit.pointer``, preserving the rest of the document.

    Raises rather than writing anything when the target exists but cannot be
    parsed, so a hand-edited config is never clobbered.
    """
    if edit.target.suffix != ".json":
        raise ValueError(f"{edit.target}: only JSON config edits are supported")
    document = _read_json_document(edit.target)
    table = document
    keys = edit.pointer.split(".")
    for key in keys[:-1]:
        nested = table.get(key)
        if nested is None:
            nested = {}
            table[key] = nested
        elif not isinstance(nested, dict):
            raise ValueError(f"{edit.target}: {key!r} in {edit.pointer!r} is not a table")
        table = nested
    table[keys[-1]] = edit.value
    _write_atomically(edit.target, json.dumps(document, indent=2) + "\n")


@dataclass
class _Interruption:
    signum: int | None = None


@contextmanager
def _signal_scope(runner: CommandRunner) -> Iterator[_Interruption]:
    """Forward SIGINT/SIGTERM to the active child and record the interruption."""
    state = _Interruption()

    def handle(signum: int, _frame: object) -> None:
        state.signum = signum
        if isinstance(runner, SignalForwardingRunner):
            runner.forward_signal(signum)

    previous: dict[int, Any] = {}
    try:
        unavailable: list[str] = []
        for number in (signal.SIGINT, signal.SIGTERM):
            try:
                previous[number] = signal.signal(number, handle)
            except ValueError:
                unavailable.append(number.name)
        if unavailable:
            print(
                f"warning: no interrupt handling for {', '.join(unavailable)} "
                "(apply is not running on the main thread); an interrupted run "
                "will not be reported as interrupted",
                file=sys.stderr,
            )
        yield state
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _blocking_reason(
    step: PlanStep, unmet: set[str], repositories: _RepositoryRevalidation
) -> str | None:
    blocking = [dependency for dependency in step.depends_on if dependency in unmet]
    if blocking:
        return f"blocked by unmet dependencies: {', '.join(blocking)}"
    if step.repository is None:
        return None
    return repositories.drift(step.repository)


def _perform(
    step: PlanStep,
    adapters: ComponentAdapters,
    runner: CommandRunner,
    interruption: _Interruption,
) -> StepResult:
    adapter = adapter_for(step, adapters)
    started = time.monotonic()
    if adapter.check_postcondition(step, runner):
        return step_result(step, StepStatus.SKIPPED, elapsed_ms=elapsed_ms(started))

    outcome: CommandOutcome | None = None
    failure: str | None = None
    if step.config_edit is not None:
        try:
            apply_config_edit(step.config_edit)
        except (OSError, ValueError) as error:
            failure = str(error)
    else:
        outcome = runner.run(step.argv, cwd=step.repository)

    if adapter.check_postcondition(step, runner):
        status = StepStatus.SUCCEEDED
    elif interruption.signum is not None:
        status = StepStatus.INTERRUPTED
    else:
        status = StepStatus.FAILED
    # A discarded write is a diagnostic even when the postcondition ends up
    # satisfied by something else (a concurrent editor, a pre-existing entry).
    remediation = failure
    if status is StepStatus.FAILED:
        unsatisfied = f"postcondition still unsatisfied: {step.postcondition}"
        remediation = f"{failure}; {unsatisfied}" if failure else unsatisfied
    return step_result(
        step,
        status,
        outcome=outcome,
        elapsed_ms=elapsed_ms(started),
        remediation=remediation,
        failure=failure,
    )


def _not_started(step: PlanStep) -> StepResult:
    return step_result(
        step, StepStatus.INTERRUPTED, remediation="not started: the run was interrupted"
    )


def step_result(
    step: PlanStep,
    status: StepStatus,
    *,
    outcome: CommandOutcome | None = None,
    elapsed_ms: int = 0,
    remediation: str | None = None,
    failure: str | None = None,
) -> StepResult:
    argv, secrets = scan_argv(step.argv)
    stderr = None if outcome is None else outcome.stderr
    if failure is not None:
        stderr = f"{stderr}\n{failure}" if stderr else failure
    return StepResult(
        step_id=step.step_id,
        component=step.component,
        harness=step.harness,
        repository=step.repository,
        phase=step.phase,
        argv=argv,
        config_edit=config_edit_summary(step),
        postcondition=step.postcondition,
        status=status,
        exit_code=None if outcome is None else outcome.exit_code,
        stdout_tail=None if outcome is None else _tail(outcome.stdout, secrets),
        stderr_tail=None if stderr is None else _tail(stderr, secrets),
        elapsed_ms=elapsed_ms,
        remediation=remediation,
    )


def config_edit_summary(step: PlanStep) -> ConfigEditSummary | None:
    """Identify the file a config-edit step writes; its argv is empty by design."""
    if step.config_edit is None:
        return None
    return ConfigEditSummary(target=step.config_edit.target, pointer=step.config_edit.pointer)


class _RepositoryRevalidation:
    """Recanonicalizes each repository before it is first mutated (spec:109).

    Collisions are properties of the whole selected set, so one pass discovers
    every planned repository at once and keeps all of its verdicts. Nothing on
    disk can have moved until a step mutates something, so the pass is repeated
    only after a mutation — not once per repository.
    """

    def __init__(self, plan: InstallPlan) -> None:
        self._repositories = tuple(
            dict.fromkeys(step.repository for step in plan.steps if step.repository is not None)
        )
        self._generation = 0
        self._verdicts: dict[Path, tuple[int, str | None]] = {}

    def note_mutation(self) -> None:
        """Record that a step changed the system, retiring every cached verdict."""
        self._generation += 1

    def drift(self, repository: Path) -> str | None:
        """Return why ``repository`` must not be mutated, or ``None`` if it is sound."""
        canonical = canonicalize(repository)
        cached = self._verdicts.get(canonical)
        if cached is None or cached[0] != self._generation:
            self._rediscover()
            cached = self._verdicts.get(canonical)
        if cached is None:
            return f"{repository} is no longer a repository at its planned path"
        return cached[1]

    def _rediscover(self) -> None:
        candidates = {
            candidate.canonical_path: candidate
            for candidate in discover_repositories(self._repositories, 0)
        }
        self._verdicts = {
            canonicalize(planned): (
                self._generation,
                _drift_reason(candidates.get(canonicalize(planned)), planned),
            )
            for planned in self._repositories
        }


def _drift_reason(candidate: RepositoryCandidate | None, repository: Path) -> str | None:
    if candidate is None:
        return f"{repository} is no longer a repository at its planned path"
    if not candidate.writable:
        return f"{repository} is not writable"
    if candidate.collision is not CollisionClass.NONE:
        return (
            f"{repository} now collides ({candidate.collision.value}) with another "
            "selected repository"
        )
    return None


def _tail(text: str, secrets: Sequence[str]) -> str | None:
    if not text:
        return None
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text[-TAIL_LIMIT:]


def _read_json_document(target: Path) -> dict[str, Any]:
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        document = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as error:
        raise ValueError(f"{target}: existing config is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{target}: existing config is not a JSON object")
    return document


def _write_atomically(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
