"""Hallouminate adapter: global npm install, harness registration, repo indexing."""

from __future__ import annotations

from cheese_flow.models import CommandRunner, ComponentName, DesiredState, PlanStep


class HallouminateAdapter:
    """Global versioned npm install, native plugins or MCP entry, and repo init."""

    name: ComponentName = "hallouminate"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Resolve ``hallouminate@latest`` once and emit versioned argv."""
        raise NotImplementedError

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Check executable version, registration, ``config validate``, or corpus health."""
        raise NotImplementedError
