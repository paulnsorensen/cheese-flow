"""easy-cheese adapter: ``gh skill`` install and verification."""

from __future__ import annotations

from cheese_flow.models import CommandRunner, ComponentName, DesiredState, PlanStep


class EasyCheeseAdapter:
    """Installs the easy-cheese skill pack per harness through ``gh skill``."""

    name: ComponentName = "easy-cheese"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit one ``gh skill install`` step per selected harness."""
        raise NotImplementedError

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm source, agent, scope, and installed skills via ``gh skill list``."""
        raise NotImplementedError
