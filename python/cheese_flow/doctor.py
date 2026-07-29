"""Verification of declared managed state."""

from __future__ import annotations

from cheese_flow.models import CommandRunner, ComponentAdapters, DesiredState, DoctorReport


def verify_desired_state(
    state: DesiredState, adapters: ComponentAdapters, runner: CommandRunner
) -> DoctorReport:
    """Check every postcondition ``state`` implies without changing managed state."""
    raise NotImplementedError
