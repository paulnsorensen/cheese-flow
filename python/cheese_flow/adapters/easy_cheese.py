"""easy-cheese adapter: ``skills`` CLI install and on-disk verification."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.adapters.native_config import claude_config_dir
from cheese_flow.models import (
    HARNESS_NAMES,
    CommandRunner,
    ComponentName,
    DesiredState,
    HarnessName,
    Phase,
    PlanStep,
)

SOURCE_REPOSITORY = "paulnsorensen/easy-cheese"
PACKAGE = "skills@latest"

AGENT_TOKENS: dict[HarnessName, str] = {
    "claude-code": "claude-code",
    "codex": "codex",
    "cursor": "cursor",
}
"""``skills --agent`` tokens the CLI accepts, keyed by harness.

Taken from the CLI's own agent registry. A harness that has no accepted token
belongs nowhere in this table: it then contributes no step at all, rather than
one that could only ever fail.
"""

CORE_SKILLS = frozenset({"mold", "cook", "press", "age", "cure", "plate", "cheese"})
"""The pipeline skills easy-cheese always ships; a full quorum identifies the pack."""

SKILL_FILE = "SKILL.md"
"""The file every installed skill directory carries."""


_SKILLS_DIRS: dict[HarnessName, str] = {
    "claude-code": ".claude/skills",
    "codex": ".agents/skills",
    "cursor": ".agents/skills",
}
"""Where a global ``skills add`` leaves each harness's pack, relative to home.

``.agents/skills`` is the CLI's one canonical store; a harness that declares
that shared layout as its own — Codex and Cursor — is served from it directly,
with no second copy and no link. Claude Code declares a directory of its own
and additionally receives a symlink per skill into it.

Every harness needs an entry here and in :data:`AGENT_TOKENS`. Both lookups
raise on a harness that has neither, which is the point: verifying the wrong
directory would report an install that never reached the harness.
"""


def skills_directory(harness: HarnessName) -> Path:
    """Where ``skills add --global`` leaves the pack for ``harness``.

    Claude Code's location moves with ``CLAUDE_CONFIG_DIR``, exactly as the CLI
    reads it.

    Symlinking is the CLI's default and is kept deliberately: one copy of the
    pack is updated in place, and a chezmoi-managed ``~/.claude/skills`` gains
    links rather than eighteen duplicated skill trees.
    """
    if harness == "claude-code":
        return claude_config_dir() / "skills"
    return Path.home() / _SKILLS_DIRS[harness]


class EasyCheeseAdapter:
    """Installs the easy-cheese skill pack per harness through the ``skills`` CLI."""

    name: ComponentName = "easy-cheese"

    def __init__(self, runner: CommandRunner) -> None:
        # Constructed uniformly with every other adapter, but this one resolves
        # no versions and probes with no command, so the runner is not kept.
        del runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit one ``skills add`` step per selected harness the CLI can target.

        ``npx`` runs the CLI, so the only host prerequisite is the ``npm``
        toolchain hallouminate's own install already requires.
        """
        if self.name not in state.components:
            return ()
        return tuple(
            PlanStep(
                step_id=f"easy-cheese:install:{harness}",
                component=self.name,
                harness=harness,
                phase=Phase.REGISTER,
                argv=(
                    "npx",
                    "-y",
                    PACKAGE,
                    "add",
                    SOURCE_REPOSITORY,
                    "--skill",
                    "*",
                    "--agent",
                    AGENT_TOKENS[harness],
                    "--global",
                    "--yes",
                ),
                postcondition=(
                    f"the easy-cheese core skills are installed under {skills_directory(harness)}"
                ),
            )
            for harness in HARNESS_NAMES
            if harness in state.harnesses and harness in AGENT_TOKENS
        )

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm the whole core quorum is on disk for the harness.

        The ``skills`` CLI records no provenance any listing could report, so
        identity is the pack's own layout: every core skill present as
        ``<skills dir>/<name>/SKILL.md``. That is a name-based check — a
        machine whose author keeps hand-written skills under all seven names
        reads as installed — and it is knowingly weaker than the provenance
        field the previous listing-based check read, which issue #86 found
        empty in practice anyway. It spawns no child process, so a host with no
        GitHub CLI verifies exactly as well as one that has it.
        """
        del runner  # The end state is on disk; no command can report it better.
        directory = skills_directory(_harness_of(step))
        return all((directory / name / SKILL_FILE).is_file() for name in CORE_SKILLS)


def _harness_of(step: PlanStep) -> HarnessName:
    if step.harness is None:
        raise ValueError(f"step {step.step_id!r} has no harness")
    return step.harness
