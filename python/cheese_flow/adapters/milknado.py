"""Milknado adapter: pinned MCP-server install plus Claude Code registration.

The Milknado plugin's own ``.mcp.json`` launches its server with
``uvx --from git+...@main milknado-mcp`` — an unpinned, cold source build (~90s
of downloading and compiling a heavy dependency tree) that must both materialize
the plugin cache and finish inside the session-start window. In Claude Cloud it
did neither reliably, so the ``milknado`` MCP tools never came up.

So cheese-flow stops relying on that lazy build. It installs a pinned PyPI wheel
once with ``uv tool install`` (paid in the install phase, where it can finish and
persists into the cached container) and registers the resulting ``milknado-mcp``
binary as a direct user-scope MCP entry — which launches in seconds and does not
depend on the plugin cache materializing. The plugin is still declared so its
agents and commands load; the direct entry is the authoritative MCP surface.

Codex and Cursor are deferred entirely: adding them later should extract the
shared plugin-CLI/cursor helpers from hallouminate.py rather than duplicate them
here.
"""

from __future__ import annotations

from pathlib import Path

from cheese_flow.adapters.native_config import (
    claude_config_dir,
    config_edit_holds,
    mcp_entry_holds,
    mcp_permission_edit,
)
from cheese_flow.adapters.tilth import _bin_dir
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
"""The plugin-scoped tool namespace ``mcp__plugin_milknado_milknado__*``."""

MCP_VERSION = "0.2.1"
"""Pinned PyPI wheel for the ``milknado-mcp`` server, decoupled from the plugin cut.

A version pin, not ``@main``: an unpinned spec re-resolves and rebuilds from source
on every marketplace advance, which is exactly the cold-build cost this avoids.
"""

MCP_SERVER_BIN = "milknado-mcp"
"""The console script ``uv tool install`` exposes for the MCP server."""

PROBE_BIN = "milknado"
"""The companion CLI ``uv tool install`` exposes; ``--help`` proves the install."""

CLAUDE_MCP_CONFIG = ".claude.json"
"""Claude Code's user-scope MCP surface, relative to the home directory."""

CLAUDE_MARKETPLACE_ENTRY: dict[str, object] = {
    "source": {"source": "github", "repo": MARKETPLACE_SOURCE}
}
"""The ``extraKnownMarketplaces`` entry Claude Code fetches the catalog from at startup."""

_INSTALL_STEP = "milknado:install"
_MARKETPLACE_STEP = "milknado:marketplace:claude-code"
_PLUGIN_STEP = "milknado:plugin:claude-code"
_PERMISSION_STEP = "milknado:permission:claude-code"
_MCP_STEP = "milknado:mcp:claude-code"
_MCP_PERMISSION_STEP = "milknado:permission-mcp:claude-code"


def _mcp_entry() -> dict[str, object]:
    """The direct user-scope MCP entry launching the installed server binary."""
    return {"command": str(_bin_dir() / MCP_SERVER_BIN), "args": []}


class MilknadoAdapter:
    """Installs the pinned MCP server and declares Claude Code registration.

    Claude Code reads ``extraKnownMarketplaces``/``enabledPlugins`` from user
    settings at startup and fetches the marketplace itself, so declaring those
    entries converges on a headless host with no ``claude`` on PATH. The MCP
    server, in contrast, is installed here and wired as a direct ``mcpServers``
    entry rather than left to the plugin's lazy ``uvx`` launch.
    """

    name: ComponentName = "milknado"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit the pinned install plus Claude Code registration; other harnesses deferred."""
        if self.name not in state.components:
            return ()
        if "claude-code" not in state.harnesses:
            return ()

        probe = _bin_dir() / PROBE_BIN
        settings = claude_config_dir() / "settings.json"
        mcp_config = Path.home() / CLAUDE_MCP_CONFIG

        marketplace = ConfigEdit(
            target=settings,
            pointer=f"extraKnownMarketplaces.{MARKETPLACE_NAME}",
            value=CLAUDE_MARKETPLACE_ENTRY,
        )
        plugin = ConfigEdit(target=settings, pointer=f"enabledPlugins.{PLUGIN_ID}", value=True)
        plugin_permission = mcp_permission_edit("claude-code", PACKAGE, claude_server=CLAUDE_SERVER)
        mcp = ConfigEdit(target=mcp_config, pointer=f"mcpServers.{PACKAGE}", value=_mcp_entry())
        mcp_permission = mcp_permission_edit("claude-code", PACKAGE)
        return (
            PlanStep(
                step_id=_INSTALL_STEP,
                component=self.name,
                phase=Phase.INSTALL,
                argv=("uv", "tool", "install", f"{PACKAGE}=={MCP_VERSION}"),
                postcondition=f"`{probe} --help` exits 0",
            ),
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
                config_edit=plugin_permission,
                postcondition=(
                    f"{plugin_permission.target} configures {plugin_permission.pointer} as "
                    f"{plugin_permission.value!r}"
                ),
                depends_on=(_PLUGIN_STEP,),
            ),
            PlanStep(
                step_id=_MCP_STEP,
                component=self.name,
                harness="claude-code",
                phase=Phase.REGISTER,
                config_edit=mcp,
                postcondition=(
                    f"~/{CLAUDE_MCP_CONFIG} holds {mcp.pointer} running `{MCP_SERVER_BIN}`"
                ),
                depends_on=(_INSTALL_STEP,),
            ),
            PlanStep(
                step_id=_MCP_PERMISSION_STEP,
                component=self.name,
                harness="claude-code",
                phase=Phase.REGISTER,
                config_edit=mcp_permission,
                postcondition=(
                    f"{mcp_permission.target} configures {mcp_permission.pointer} as "
                    f"{mcp_permission.value!r}"
                ),
                depends_on=(_MCP_STEP,),
            ),
        )

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Probe the installed binary, the direct MCP entry, or the settings edits."""
        if step.step_id == _INSTALL_STEP:
            return runner.run((str(_bin_dir() / PROBE_BIN), "--help")).exit_code == 0
        if step.step_id == _MCP_STEP:
            if step.config_edit is None:
                raise ValueError(f"{step.step_id!r} has no MCP config entry")
            return mcp_entry_holds(step.config_edit, "claude-code", PACKAGE)
        if step.step_id in (
            _MARKETPLACE_STEP,
            _PLUGIN_STEP,
            _PERMISSION_STEP,
            _MCP_PERMISSION_STEP,
        ):
            return step.config_edit is not None and config_edit_holds(step.config_edit)
        raise ValueError(f"{step.step_id!r} is not a milknado step")
