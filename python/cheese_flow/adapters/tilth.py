"""Tilth adapter: config-preserving MCP registration per harness."""

from __future__ import annotations

from cheese_flow.models import CommandRunner, ComponentName, DesiredState, PlanStep


class TilthAdapter:
    """Registers Tilth's MCP server in each selected harness's native config."""

    name: ComponentName = "tilth"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Resolve ``tilth@latest`` once and emit ``npx tilth@<version> install`` steps."""
        raise NotImplementedError

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm the harness config holds the expected Tilth MCP command and edit mode."""
        raise NotImplementedError
