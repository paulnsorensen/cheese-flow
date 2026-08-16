"""Milknado adapter: Claude Code plugin registration only.

Milknado's plugin ``.mcp.json`` launches its server with
``uvx --from git+...@main milknado-mcp``, so cheese-flow installs nothing —
the first launch self-fetches from the bleeding-edge default branch, which is
intentional for this cut. Codex and Cursor are deferred entirely: adding them
later should extract the shared plugin-CLI/cursor helpers from
hallouminate.py rather than duplicate them here.
"""

from __future__ import annotations

from cheese_flow.adapters.native_config import (
    claude_config_dir,
    config_edit_holds,
    mcp_permission_edit,
)
from cheese_flow.models import (
    CommandRunner,
    ComponentName,
    ConfigEdit,
    DesiredState,
    Phase,
    PlanStep,
)

PACKAGE = "milknado"
MARKETPLACE_SOURCE = "paulnsorensen/milknado"
MARKETPLACE_NAME = "milknado"
PLUGIN_ID = "milknado@milknado"
CLAUDE_SERVER = "plugin_milknado_milknado"
"""Matches the live tool namespace ``mcp__plugin_milknado_milknado__*``."""

CLAUDE_MARKETPLACE_ENTRY: dict[str, object] = {
    "source": {"source": "github", "repo": MARKETPLACE_SOURCE}
}
"""The ``extraKnownMarketplaces`` entry Claude Code fetches the catalog from at startup."""

_MARKETPLACE_STEP = "milknado:marketplace:claude-code"
_PLUGIN_STEP = "milknado:plugin:claude-code"
_PERMISSION_STEP = "milknado:permission:claude-code"


class MilknadoAdapter:
    """Declares Milknado's Claude Code plugin registration in user settings.

    Mirrors Hallouminate's ``_claude_registration_steps``: Claude Code reads
    ``extraKnownMarketplaces`` and ``enabledPlugins`` from user settings at
    startup and fetches the marketplace itself, so declaring the entries
    converges on a headless host with no ``claude`` on PATH.
    """

    name: ComponentName = "milknado"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit Claude Code registration steps only; other harnesses are deferred."""
        if self.name not in state.components:
            return ()
        if "claude-code" not in state.harnesses:
            return ()

        settings = claude_config_dir() / "settings.json"
        marketplace = ConfigEdit(
            target=settings,
            pointer=f"extraKnownMarketplaces.{MARKETPLACE_NAME}",
            value=CLAUDE_MARKETPLACE_ENTRY,
        )
        plugin = ConfigEdit(target=settings, pointer=f"enabledPlugins.{PLUGIN_ID}", value=True)
        permission = mcp_permission_edit("claude-code", PACKAGE, claude_server=CLAUDE_SERVER)
        return (
            PlanStep(
                step_id=_MARKETPLACE_STEP,
                component=self.name,
                harness="claude-code",
                phase=Phase.REGISTER,
                config_edit=marketplace,
                postcondition=(
                    f"{settings} declares the {MARKETPLACE_SOURCE} marketplace at "
                    f"{marketplace.pointer}"
                ),
                depends_on=(),
            ),
            PlanStep(
                step_id=_PLUGIN_STEP,
                component=self.name,
                harness="claude-code",
                phase=Phase.REGISTER,
                config_edit=plugin,
                postcondition=f"{settings} enables {PLUGIN_ID} at {plugin.pointer}",
                depends_on=(_MARKETPLACE_STEP,),
            ),
            PlanStep(
                step_id=_PERMISSION_STEP,
                component=self.name,
                harness="claude-code",
                phase=Phase.REGISTER,
                config_edit=permission,
                postcondition=(
                    f"{permission.target} configures {permission.pointer} as {permission.value!r}"
                ),
                depends_on=(_PLUGIN_STEP,),
            ),
        )

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Every step's postcondition is the settings file itself."""
        if step.step_id in (_MARKETPLACE_STEP, _PLUGIN_STEP, _PERMISSION_STEP):
            return step.config_edit is not None and config_edit_holds(step.config_edit)
        raise ValueError(f"{step.step_id!r} is not a milknado step")
