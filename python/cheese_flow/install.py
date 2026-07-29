"""Deterministic planning and verified apply."""

from __future__ import annotations

from cheese_flow.models import (
    ApplyReport,
    CommandRunner,
    ComponentAdapters,
    DesiredState,
    InstallPlan,
)


def build_install_plan(state: DesiredState, adapters: ComponentAdapters) -> InstallPlan:
    """Resolve component versions once and emit the ordered, versioned plan."""
    raise NotImplementedError


def apply_install_plan(plan: InstallPlan, runner: CommandRunner) -> ApplyReport:
    """Run the plan, skipping steps whose postcondition already holds.

    A failed postcondition blocks dependent steps; unrelated components and
    repositories continue. There is no rollback.
    """
    raise NotImplementedError
