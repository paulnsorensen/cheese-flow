"""easy-cheese adapter: ``gh skill`` install and verification."""

from __future__ import annotations

import json
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

SOURCE_REPOSITORY = "paulnsorensen/easy-cheese"
SCOPE = "user"

_LIST_FIELDS = "agentHosts,scope,skillName,sourceURL"

CORE_SKILLS = frozenset({"mold", "cook", "press", "age", "cure", "plate", "cheese"})
"""The pipeline skills easy-cheese always ships; a full quorum identifies the pack."""


def _normalize_source(raw: str) -> str:
    """Reduce a ``gh skill list`` sourceURL to its ``owner/repo`` identity."""
    trimmed = raw.strip().removesuffix(".git").rstrip("/")
    if not trimmed:
        return ""
    parts = [part for part in trimmed.split("/") if part]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


class EasyCheeseAdapter:
    """Installs the easy-cheese skill pack per harness through ``gh skill``."""

    name: ComponentName = "easy-cheese"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit one ``gh skill install`` step per selected harness."""
        if self.name not in state.components:
            return ()
        return tuple(
            PlanStep(
                step_id=f"easy-cheese:install:{harness}",
                component=self.name,
                harness=harness,
                phase=Phase.REGISTER,
                argv=(
                    "gh",
                    "skill",
                    "install",
                    SOURCE_REPOSITORY,
                    "--all",
                    "--agent",
                    harness,
                    "--scope",
                    SCOPE,
                ),
                postcondition=(
                    f"`gh skill list` reports {SOURCE_REPOSITORY} skills for {harness} at "
                    f"{SCOPE} scope"
                ),
            )
            for harness in HARNESS_NAMES
            if harness in state.harnesses
        )

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm the pack is installed for the harness at the expected scope.

        ``gh skill install`` records provenance in the installed ``SKILL.md``'s
        ``metadata.github-repo`` frontmatter, which ``gh skill list`` surfaces
        as ``sourceURL``. The field is empty exactly when gh did not install the
        skill, so it is authoritative identity: locally authored skills that
        merely share easy-cheese's names never count. The step installs
        ``--all``, so convergence needs the whole core quorum from our source.
        """
        if step.harness is None:
            raise ValueError(f"step {step.step_id!r} has no harness")
        outcome = runner.run(
            (
                "gh",
                "skill",
                "list",
                "--agent",
                step.harness,
                "--scope",
                SCOPE,
                "--json",
                _LIST_FIELDS,
            )
        )
        if outcome.exit_code != 0:
            return False
        try:
            entries = json.loads(outcome.stdout)
        except json.JSONDecodeError:
            return False
        if not isinstance(entries, list):
            return False
        ours = {
            str(entry["skillName"]).strip()
            for entry in entries
            if _is_skill_for(entry, step.harness)
            and _normalize_source(str(entry.get("sourceURL", ""))) == SOURCE_REPOSITORY
        }
        return ours >= CORE_SKILLS


def _is_skill_for(entry: Any, harness: HarnessName) -> bool:
    """Whether a listing entry is a named skill installed for this harness and scope."""
    if not isinstance(entry, dict):
        return False
    if entry.get("scope") != SCOPE:
        return False
    hosts = entry.get("agentHosts")
    if not isinstance(hosts, list) or harness not in hosts:
        return False
    return bool(str(entry.get("skillName", "")).strip())
