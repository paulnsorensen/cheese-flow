"""Hallouminate adapter: global npm install, harness registration, repo indexing."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.models import (
    HARNESS_NAMES,
    CommandRunner,
    ComponentName,
    DesiredState,
    HarnessName,
    Phase,
    PlanStep,
)

PACKAGE = "hallouminate"
MARKETPLACE_SOURCE = "paulnsorensen/hallouminate"
PLUGIN_ID = "hallouminate@hallouminate"

# Harness-native plugin CLIs, keyed by harness: (executable, install verb).
# Cursor is absent on purpose — it receives MCP and CLI integration, never
# Hallouminate plugin workflows.
PLUGIN_CLIS: dict[HarnessName, tuple[str, str]] = {
    "claude-code": ("claude", "install"),
    "codex": ("codex", "add"),
}

_INSTALL_STEP = "hallouminate:npm-install"
_CONFIG_STEP = "hallouminate:config-init"


def _corpus_name(repository: Path) -> str:
    """The corpus `hallouminate init-repo <name>` seeds for a repository."""
    return f"repo:{repository.name}:wiki"


class HallouminateAdapter:
    """Global versioned npm install, native plugins or MCP entry, and repo init."""

    name: ComponentName = "hallouminate"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner
        self._version: str | None = None

    def resolved_version(self) -> str:
        """Resolve ``hallouminate@latest`` once per run and cache it in memory."""
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
        """Resolve ``hallouminate@latest`` once and emit versioned argv."""
        if self.name not in state.components:
            return ()

        version = self.resolved_version()
        harnesses = tuple(h for h in HARNESS_NAMES if h in state.harnesses)

        steps: list[PlanStep] = [
            PlanStep(
                step_id=_INSTALL_STEP,
                component=self.name,
                phase=Phase.INSTALL,
                argv=("npm", "install", "-g", f"{PACKAGE}@{version}"),
                postcondition=f"`hallouminate --version` reports {version}",
            )
        ]

        for harness in harnesses:
            if harness not in PLUGIN_CLIS:
                continue
            executable, verb = PLUGIN_CLIS[harness]
            steps.append(
                PlanStep(
                    step_id=f"hallouminate:marketplace:{harness}",
                    component=self.name,
                    harness=harness,
                    phase=Phase.REGISTER,
                    argv=(executable, "plugin", "marketplace", "add", MARKETPLACE_SOURCE),
                    postcondition=(
                        f"`{executable} plugin marketplace list` lists {MARKETPLACE_SOURCE}"
                    ),
                    depends_on=(_INSTALL_STEP,),
                )
            )
            steps.append(
                PlanStep(
                    step_id=f"hallouminate:plugin:{harness}",
                    component=self.name,
                    harness=harness,
                    phase=Phase.REGISTER,
                    argv=(executable, "plugin", verb, PLUGIN_ID),
                    postcondition=f"`{executable} plugin list` lists {PLUGIN_ID}",
                    depends_on=(f"hallouminate:marketplace:{harness}",),
                )
            )

        steps.append(
            PlanStep(
                step_id=_CONFIG_STEP,
                component=self.name,
                phase=Phase.CONFIGURE,
                argv=("hallouminate", "config", "init"),
                postcondition="`hallouminate config validate` succeeds",
                depends_on=(_INSTALL_STEP,),
            )
        )

        for repository in state.repositories.selected:
            key = repository.as_posix()
            init_id = f"hallouminate:init-repo:{key}"
            steps.append(
                PlanStep(
                    step_id=init_id,
                    component=self.name,
                    repository=repository,
                    phase=Phase.INITIALIZE,
                    argv=("hallouminate", "init-repo", repository.name, "--path", str(repository)),
                    postcondition=(
                        f"`hallouminate config validate` in {key} reports "
                        f"{_corpus_name(repository)}"
                    ),
                    depends_on=(_CONFIG_STEP,),
                )
            )
            steps.append(
                PlanStep(
                    step_id=f"hallouminate:index:{key}",
                    component=self.name,
                    repository=repository,
                    phase=Phase.INITIALIZE,
                    argv=(
                        "hallouminate",
                        "index",
                        "--corpus",
                        _corpus_name(repository),
                        "--strict",
                    ),
                    postcondition=f"`hallouminate ground` answers from {_corpus_name(repository)}",
                    depends_on=(init_id,),
                )
            )

        return tuple(steps)

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Check executable version, registration, ``config validate``, or corpus health."""
        if step.step_id == _INSTALL_STEP:
            return self._check_version(runner)
        if step.step_id.startswith("hallouminate:marketplace:"):
            return self._check_marketplace(step, runner)
        if step.step_id.startswith("hallouminate:plugin:"):
            return self._check_plugin(step, runner)
        if step.step_id == _CONFIG_STEP:
            return runner.run(("hallouminate", "config", "validate")).exit_code == 0
        if step.step_id.startswith("hallouminate:init-repo:"):
            return self._check_repo_config(step, runner)
        if step.step_id.startswith("hallouminate:index:"):
            return self._check_corpus_query(step, runner)
        raise ValueError(f"{step.step_id!r} is not a hallouminate step")

    def _check_version(self, runner: CommandRunner) -> bool:
        outcome = runner.run(("hallouminate", "--version"))
        if outcome.exit_code != 0:
            return False
        return self.resolved_version() in outcome.stdout.split()

    def _check_marketplace(self, step: PlanStep, runner: CommandRunner) -> bool:
        executable, _ = PLUGIN_CLIS[_harness_of(step)]
        outcome = runner.run((executable, "plugin", "marketplace", "list"))
        return outcome.exit_code == 0 and MARKETPLACE_SOURCE.split("/")[-1] in outcome.stdout

    def _check_plugin(self, step: PlanStep, runner: CommandRunner) -> bool:
        executable, _ = PLUGIN_CLIS[_harness_of(step)]
        outcome = runner.run((executable, "plugin", "list"))
        return outcome.exit_code == 0 and PLUGIN_ID in outcome.stdout

    def _check_repo_config(self, step: PlanStep, runner: CommandRunner) -> bool:
        repository = _repository_of(step)
        outcome = runner.run(("hallouminate", "config", "validate"), cwd=repository)
        return outcome.exit_code == 0 and _corpus_name(repository) in outcome.stdout

    def _check_corpus_query(self, step: PlanStep, runner: CommandRunner) -> bool:
        repository = _repository_of(step)
        outcome = runner.run(
            (
                "hallouminate",
                "ground",
                _corpus_name(repository),
                "--corpus",
                _corpus_name(repository),
                "--format",
                "json",
                "--limit",
                "1",
            ),
            cwd=repository,
        )
        return outcome.exit_code == 0 and '"path"' in outcome.stdout


def _harness_of(step: PlanStep) -> HarnessName:
    if step.harness is None:
        raise ValueError(f"step {step.step_id!r} has no harness")
    return step.harness


def _repository_of(step: PlanStep) -> Path:
    if step.repository is None:
        raise ValueError(f"step {step.step_id!r} has no repository")
    return step.repository
