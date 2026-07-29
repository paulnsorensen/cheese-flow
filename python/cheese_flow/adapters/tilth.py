"""Tilth adapter: config-preserving MCP registration per harness."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

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

EXPECTED_COMMAND = "npx"
"""``tilth install`` writes an ``npx`` entry when it runs from a node_modules shim."""

EXPECTED_ARGS: tuple[str, ...] = ("tilth", "--mcp", "--edit")
"""Edit mode is always requested, so ``--edit`` must be present in the entry."""

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
        entry = _read_entry(Path.home() / _CONFIG_PATHS[step.harness], step.harness)
        if not isinstance(entry, dict):
            return False
        args = entry.get("args")
        if not isinstance(args, list):
            return False
        return entry.get("command") == EXPECTED_COMMAND and tuple(args) == EXPECTED_ARGS


def _read_entry(path: Path, harness: HarnessName) -> Any:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        if harness == "codex":
            return tomllib.loads(raw.decode()).get("mcp_servers", {}).get(PACKAGE)
        document = json.loads(raw)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    servers = document.get("mcpServers")
    return servers.get(PACKAGE) if isinstance(servers, dict) else None
