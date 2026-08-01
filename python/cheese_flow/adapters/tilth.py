"""Tilth adapter: config-preserving MCP registration per harness."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.adapters.native_config import read_mcp_entry
from cheese_flow.models import (
    HARNESS_NAMES,
    CommandRunner,
    ComponentName,
    DesiredState,
    HarnessName,
    Phase,
    PlanStep,
)

PACKAGE = "tilth"

EDIT_FLAG = "--edit"
"""Edit mode is always requested, so ``--edit`` must be present in the entry."""


def _launches_tilth(command: str, args: list[str]) -> bool:
    """Whether an MCP entry launches Tilth itself.

    ``tilth install`` writes ``npx tilth …`` only when it runs from a
    node_modules shim; a globally installed binary is written as its own
    absolute path instead.
    """
    if command == "npx":
        return bool(args) and args[0] == PACKAGE
    return Path(command).stem == PACKAGE


# Native user-scope MCP config per harness, relative to the home directory.
_CONFIG_PATHS: dict[HarnessName, str] = {
    "claude-code": ".claude.json",
    "codex": ".codex/config.toml",
    "cursor": ".cursor/mcp.json",
}


class TilthAdapter:
    """Registers Tilth's MCP server in each selected harness's native config."""

    name: ComponentName = "tilth"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner
        self._version: str | None = None

    def resolved_version(self) -> str:
        """Resolve ``tilth@latest`` once per run and cache it in memory."""
        if self._version is None:
            outcome = self._runner.run(("npm", "view", f"{PACKAGE}@latest", "version"))
            version = outcome.stdout.strip()
            if outcome.exit_code != 0 or not version:
                raise RuntimeError(
                    f"could not resolve {PACKAGE}@latest with npm view "
                    f"(exit {outcome.exit_code}): "
                    f"{outcome.stderr.strip() or outcome.stdout.strip()}"
                )
            self._version = version
        return self._version

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Resolve ``tilth@latest`` once and emit ``npx tilth@<version> install`` steps."""
        if self.name not in state.components:
            return ()
        version = self.resolved_version()
        return tuple(
            PlanStep(
                step_id=f"tilth:register:{harness}",
                component=self.name,
                harness=harness,
                phase=Phase.REGISTER,
                argv=("npx", "--yes", f"{PACKAGE}@{version}", "install", harness, "--edit"),
                postcondition=(f"{_CONFIG_PATHS[harness]} holds the tilth MCP entry in edit mode"),
            )
            for harness in HARNESS_NAMES
            if harness in state.harnesses
        )

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm the harness config holds the expected Tilth MCP command and edit mode."""
        if step.harness is None:
            raise ValueError(f"step {step.step_id!r} has no harness")
        entry = read_mcp_entry(Path.home() / _CONFIG_PATHS[step.harness], step.harness, PACKAGE)
        if not isinstance(entry, dict):
            return False
        args = entry.get("args")
        command = entry.get("command")
        if not isinstance(args, list) or not isinstance(command, str):
            return False
        args = [str(arg) for arg in args]
        return _launches_tilth(command, args) and "--mcp" in args and EDIT_FLAG in args
