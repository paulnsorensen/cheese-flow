"""Verification of declared managed state."""

from __future__ import annotations

import time

from cheese_flow.install import (
    adapter_for,
    build_install_plan,
    elapsed_ms,
    report_status,
    step_result,
)
from cheese_flow.models import (
    CommandRunner,
    ComponentAdapters,
    DesiredState,
    DoctorReport,
    PlanStep,
    StepResult,
    StepStatus,
)


def verify_desired_state(
    state: DesiredState, adapters: ComponentAdapters, runner: CommandRunner
) -> DoctorReport:
    """Check every postcondition ``state`` implies without changing managed state.

    Doctor runs postconditions only: it never executes a step's argv, applies a
    config edit, or writes the manifest. Every step is checked independently, so
    one unsatisfied postcondition never hides the state of the steps after it.
    """
    plan = build_install_plan(state, adapters)
    results = tuple(_verify(step, adapters, runner) for step in plan.steps)
    return DoctorReport(status=report_status(results), manifest=state, plan=plan, results=results)


def _verify(step: PlanStep, adapters: ComponentAdapters, runner: CommandRunner) -> StepResult:
    started = time.monotonic()
    satisfied = adapter_for(step, adapters).check_postcondition(step, runner)
    status = StepStatus.SUCCEEDED if satisfied else StepStatus.FAILED
    return step_result(
        step,
        status,
        elapsed_ms=elapsed_ms(started),
        remediation=(None if satisfied else f"postcondition not satisfied: {step.postcondition}"),
    )
