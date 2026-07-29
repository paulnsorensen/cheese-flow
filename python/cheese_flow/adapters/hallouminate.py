"""Hallouminate adapter: global npm install, harness registration, repo indexing."""

from __future__ import annotations

import json
from pathlib import Path

from cheese_flow.adapters.native_config import read_mcp_entry
from cheese_flow.models import (
    HARNESS_NAMES,
    CommandRunner,
    ComponentName,
    ConfigEdit,
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

CURSOR_MCP_CONFIG = ".cursor/mcp.json"
"""Cursor's user MCP surface, relative to the home directory."""

CURSOR_MCP_POINTER = f"mcpServers.{PACKAGE}"

CURSOR_MCP_ENTRY: dict[str, object] = {"command": PACKAGE, "args": ["serve"]}
"""The entry Hallouminate's own plugin ``.mcp.json`` declares for its server."""

_INSTALL_STEP = "hallouminate:npm-install"
_CONFIG_STEP = "hallouminate:config-init"
_CURSOR_MCP_STEP = "hallouminate:mcp:cursor"


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
            if harness == "cursor":
                # Cursor has no plugin or MCP-registration CLI: its user MCP
                # surface is the config file itself, so declare the edit.
                steps.append(
                    PlanStep(
                        step_id=_CURSOR_MCP_STEP,
                        component=self.name,
                        harness=harness,
                        phase=Phase.REGISTER,
                        config_edit=ConfigEdit(
                            target=Path.home() / CURSOR_MCP_CONFIG,
                            pointer=CURSOR_MCP_POINTER,
                            value=CURSOR_MCP_ENTRY,
                        ),
                        postcondition=(
                            f"~/{CURSOR_MCP_CONFIG} holds {CURSOR_MCP_POINTER} running "
                            f"`{PACKAGE} serve`"
                        ),
                        depends_on=(_INSTALL_STEP,),
                    )
                )
                continue
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
                        f"`{executable} plugin marketplace list --json` reports "
                        f"{MARKETPLACE_SOURCE}"
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
                    postcondition=(
                        f"`{executable} plugin list --json` reports {PLUGIN_ID} installed"
                    ),
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
        if step.step_id == _CURSOR_MCP_STEP:
            return _check_cursor_mcp(step)
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
        outcome = runner.run((executable, "plugin", "marketplace", "list", "--json"))
        return outcome.exit_code == 0 and MARKETPLACE_SOURCE in _marketplace_sources(outcome.stdout)

    def _check_plugin(self, step: PlanStep, runner: CommandRunner) -> bool:
        executable, _ = PLUGIN_CLIS[_harness_of(step)]
        outcome = runner.run((executable, "plugin", "list", "--json"))
        return outcome.exit_code == 0 and PLUGIN_ID in _installed_plugin_ids(outcome.stdout)

    def _check_repo_config(self, step: PlanStep, runner: CommandRunner) -> bool:
        repository = _repository_of(step)
        outcome = runner.run(("hallouminate", "config", "validate"), cwd=repository)
        if outcome.exit_code != 0:
            return False
        root = _resolved(str(repository))
        name = _corpus_name(repository)
        return any(path.is_relative_to(root) for path in _corpus_paths(outcome.stdout, name))

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


def _check_cursor_mcp(step: PlanStep) -> bool:
    """Confirm Cursor's MCP config declares the entry the step's edit specifies."""
    edit = step.config_edit
    if edit is None:
        raise ValueError(f"step {step.step_id!r} has no config edit")
    entry = read_mcp_entry(edit.target, "cursor", PACKAGE)
    if not isinstance(entry, dict):
        return False
    return entry.get("command") == edit.value["command"] and entry.get("args") == edit.value["args"]


_BULLETS = "-*•❯> \t"


def _owner_repo(raw: str) -> str:
    """Reduce a marketplace's remote source to its ``owner/repo`` identity."""
    trimmed = raw.strip().removesuffix(".git").rstrip("/")
    parts = [part for part in trimmed.split("/") if part]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


def _marketplace_sources(stdout: str) -> set[str]:
    """Remote ``owner/repo`` identities from ``plugin marketplace list --json``.

    Marketplace names collide: a directory-sourced ``hallouminate`` marketplace
    is already registered on developer machines, and it does not satisfy a step
    that added ``paulnsorensen/hallouminate``. Only entries the CLI reports as
    remotely sourced contribute, so a local root can never normalize into a
    false match. Codex answers ``{"marketplaces": [...]}`` with a nested
    ``marketplaceSource``; Claude answers a flat list keyed ``source``/``repo``.
    """
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return set()
    entries = document.get("marketplaces") if isinstance(document, dict) else document
    if not isinstance(entries, list):
        return set()
    sources: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nested = entry.get("marketplaceSource")
        if isinstance(nested, dict):
            if nested.get("sourceType") == "git":
                sources.add(_owner_repo(str(nested.get("source", ""))))
        elif entry.get("source") == "github":
            sources.add(_owner_repo(str(entry.get("repo", ""))))
    return sources - {""}


def _installed_plugin_ids(stdout: str) -> set[str]:
    """Installed plugin ids from a ``plugin list --json`` document.

    Codex answers ``{"installed": [...], "available": [...]}`` with entries
    keyed ``pluginId``; Claude answers a flat list keyed ``id``. Codex lists
    plugins its marketplaces merely offer, so ``installed: false`` entries are
    excluded — that distinction is the whole point of the check.

    Claude reports OTHER projects' project-scoped plugins in this global
    listing, so a flat entry must additionally be ``scope: "user"``. Its
    ``enabled`` flag is deliberately ignored: claude reports ``enabled: false``
    for active plugins too, so reading it would reject correct installs.
    """
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return set()
    if isinstance(document, dict):
        return _codex_plugin_ids(document.get("installed"))
    return _claude_plugin_ids(document)


def _codex_plugin_ids(entries: object) -> set[str]:
    if not isinstance(entries, list):
        return set()
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("installed") is False:
            continue
        identifier = entry.get("pluginId")
        if isinstance(identifier, str) and identifier:
            ids.add(identifier)
    return ids


def _claude_plugin_ids(entries: object) -> set[str]:
    if not isinstance(entries, list):
        return set()
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("scope") != "user":
            continue
        identifier = entry.get("id")
        if isinstance(identifier, str) and identifier:
            ids.add(identifier)
    return ids


def _resolved(raw: str) -> Path:
    """Absolute, symlink-free path for a value printed by ``config validate``."""
    return Path(raw.strip()).expanduser().resolve()


def _corpus_paths(stdout: str, name: str) -> list[Path]:
    """Directories ``config validate`` reports for the named corpus.

    ``config validate`` prints the merged XDG baseline, so the same corpus
    name can be contributed by a same-named repository elsewhere on disk;
    only the arrow target identifies which repository a corpus belongs to.

    The CLI renders ``→`` today, but a non-UTF-8 locale or a plain renderer
    emits ``->``. Missing it is silent and total — ``config validate`` still
    exits 0 — so both spellings are accepted.
    """
    paths: list[Path] = []
    for line in stdout.splitlines():
        label, arrow, target = line.partition("→")
        if not arrow:
            label, arrow, target = line.partition("->")
        if not arrow or label.strip().lstrip(_BULLETS) != name:
            continue
        paths.append(_resolved(target))
    return paths


def _harness_of(step: PlanStep) -> HarnessName:
    if step.harness is None:
        raise ValueError(f"step {step.step_id!r} has no harness")
    return step.harness


def _repository_of(step: PlanStep) -> Path:
    if step.repository is None:
        raise ValueError(f"step {step.step_id!r} has no repository")
    return step.repository
