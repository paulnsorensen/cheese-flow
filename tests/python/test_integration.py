"""End-to-end tests across the module seams five parallel curds could not test.

Everything here is real: the real ``desired_state`` loader reading a real TOML
file, the real ``default_component_adapters``, the real ``build_install_plan``,
the real ``apply_install_plan`` scheduler, the real ``verify_desired_state``,
the real wizard, and the real Typer CLI. Exactly two things are faked, both at
the outermost boundary:

* :class:`FakeWorld` stands in for ``CommandRunner`` — no npm, gh, npx, or
  network — and models the state those commands would change on a real machine.
* ``HOME`` / ``XDG_CONFIG_HOME`` / ``PATH`` are redirected into ``tmp_path``.

Each test names the spec acceptance criterion it covers by line number.
"""

from __future__ import annotations

import importlib.util
import io
import json
import signal
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
from cheese_flow import cli
from cheese_flow.adapters import default_component_adapters
from cheese_flow.adapters.tilth import RELEASE_URL, _bin_dir, _install_script, _target_triple
from cheese_flow.cli import app
from cheese_flow.desired_state import load_desired_state, save_desired_state
from cheese_flow.install import apply_install_plan, build_install_plan
from cheese_flow.models import CommandOutcome, DesiredState, StepStatus
from cheese_flow.tui import run_wizard
from cyclopts_testing import CliRunner
from pytest_bdd import given, scenarios, then, when

cli_runner = CliRunner()
scenarios("features/easy_cheese.feature")

REPO_ROOT = Path(__file__).resolve().parents[2]

MARKETPLACE_SOURCE = "paulnsorensen/hallouminate"
MARKETPLACE_NAME = "hallouminate"
PLUGIN_ID = "hallouminate@hallouminate"

# A directory-sourced marketplace of the same NAME that developer machines
# already carry: a local checkout whose path even normalizes to the very
# owner/repo the step adds. Only the CLI's remote/local distinction rejects it,
# so it must stay in the fake's output even when nothing has been added.
DECOY_MARKETPLACE = MARKETPLACE_NAME
DECOY_MARKETPLACE_ROOT = "/home/paul/Dev/paulnsorensen/hallouminate"

# What `skills add <repo> --skill '*' --global` puts on disk. Spelled out
# rather than imported: dropping one of these must fail the postcondition, not
# follow it.
EASY_CHEESE_SOURCE = "paulnsorensen/easy-cheese"
EASY_CHEESE_SKILLS = ("mold", "cook", "press", "age", "cure", "plate", "cheese")

# Where the `skills` CLI writes a global install: one canonical store, plus a
# per-skill symlink into the directory of every agent that does not read the
# canonical layout already. Codex and Cursor do read it; Claude Code does not.
CANONICAL_SKILLS_DIR = ".agents/skills"
CLAUDE_SKILLS_DIR = ".claude/skills"

# The harness-native MCP config files the adapters read. Spelled out here on
# purpose: if production moves one of these, the fake writes the old path and
# the postcondition fails, which is the outcome we want.
CLAUDE_MCP_CONFIG = ".claude.json"
CODEX_MCP_CONFIG = ".codex/config.toml"
CURSOR_MCP_CONFIG = ".cursor/mcp.json"


def tilth_entry() -> dict:
    return {"command": str(_bin_dir() / "tilth"), "args": ["--mcp", "--edit"]}


HALLOUMINATE_CURSOR_ENTRY = {"command": "hallouminate", "args": ["serve"]}


# ─── The faked outer boundary ────────────────────────────────────────────────


class FakeWorld:
    """Every child process cheese-flow would spawn, plus the state it mutates.

    Commands are answered from modelled machine state rather than a fixed
    script, so postconditions converge exactly when the corresponding mutation
    actually ran. ``versions`` maps a package to the sequence of answers
    ``npm view`` gives; the last one repeats forever, so a second resolution in
    one run is directly observable.
    """

    def __init__(
        self,
        home: Path,
        *,
        versions: dict[str, list[str]] | None = None,
        refuse: frozenset[str] = frozenset(),
        interrupt_on: tuple[str, ...] | None = None,
    ) -> None:
        self.home = home
        self._versions = {package: list(answers) for package, answers in (versions or {}).items()}
        self._refuse = refuse
        self._interrupt_on = interrupt_on
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []
        self.forwarded: list[int] = []
        self.installed: dict[str, str] = {}
        self.marketplaces: set[str] = set()
        self.plugins: set[str] = set()
        self.config_initialized = False
        self.config_exists = False
        self.initialized_repos: set[Path] = set()
        self.indexed_repos: set[Path] = set()
        self.skills: dict[str, list[str]] = {}

    # -- CommandRunner protocol ------------------------------------------------

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        key = tuple(argv)
        self.calls.append((key, cwd))
        if self._interrupt_on is not None and key == self._interrupt_on:
            signal.raise_signal(signal.SIGINT)
        return self._dispatch(key, cwd)

    def forward_signal(self, signum: int) -> None:
        self.forwarded.append(signum)

    # -- Test-facing helpers ---------------------------------------------------

    def argvs(self) -> list[tuple[str, ...]]:
        return [argv for argv, _ in self.calls]

    def count(self, argv: tuple[str, ...]) -> int:
        return self.argvs().count(argv)

    def converge(self, *, harnesses: Sequence[str], version: str = "1.0.0") -> None:
        """Bring the world to the state a successful install would leave behind."""
        self.installed["hallouminate"] = version
        self.installed["tilth"] = "nightly"
        self.marketplaces.add(MARKETPLACE_SOURCE)
        self.plugins.add(PLUGIN_ID)
        self.config_exists = True
        self.config_initialized = True
        for harness in harnesses:
            self.install_skills(harness)
            self.write_tilth_entry(harness)
        if "claude-code" in harnesses:
            settings = self.home / ".claude/settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            document = _read_json(settings)
            document.setdefault("permissions", {}).setdefault("allow", []).extend(
                ["mcp__plugin_hallouminate_hallouminate__*", "mcp__tilth__*"]
            )
            document["extraKnownMarketplaces"] = {
                MARKETPLACE_NAME: {"source": {"source": "github", "repo": MARKETPLACE_SOURCE}}
            }
            document["enabledPlugins"] = {PLUGIN_ID: True}
            settings.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        if "codex" in harnesses:
            config = self.home / CODEX_MCP_CONFIG
            config.write_text(
                config.read_text(encoding="utf-8")
                + '\ndefault_tools_approval_mode = "approve"\n'
                + "\n[plugins.hallouminate.mcp_servers.hallouminate]\n"
                + 'default_tools_approval_mode = "approve"\n',
                encoding="utf-8",
            )
        if "cursor" in harnesses:
            config = self.home / ".cursor/cli-config.json"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                json.dumps(
                    {"permissions": {"allow": ["Mcp(hallouminate:*)", "Mcp(tilth:*)"]}},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    def install_skills(self, harness: str) -> None:
        """What ``skills add <repo> --skill '*' --agent <harness> --global`` leaves on disk."""
        self.skills[harness] = list(EASY_CHEESE_SKILLS)
        canonical = self.home / CANONICAL_SKILLS_DIR
        for name in EASY_CHEESE_SKILLS:
            (canonical / name).mkdir(parents=True, exist_ok=True)
            (canonical / name / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        if harness == "claude-code":
            linked = self.home / CLAUDE_SKILLS_DIR
            linked.mkdir(parents=True, exist_ok=True)
            for name in EASY_CHEESE_SKILLS:
                link = linked / name
                if not link.exists():
                    link.symlink_to(canonical / name, target_is_directory=True)

    def write_tilth_entry(self, harness: str) -> None:
        """What ``tilth install <harness> --edit`` leaves in the native config."""
        binary = str(_bin_dir() / "tilth")
        if harness == "codex":
            path = self.home / CODEX_MCP_CONFIG
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            entry = f'[mcp_servers.tilth]\ncommand = "{binary}"\nargs = ["--mcp", "--edit"]\n'
            path.write_text(f"{existing}\n{entry}" if existing else entry, encoding="utf-8")
            return
        path = self.home / (CLAUDE_MCP_CONFIG if harness == "claude-code" else CURSOR_MCP_CONFIG)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = _read_json(path)
        document.setdefault("mcpServers", {})["tilth"] = tilth_entry()
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    # -- Command modelling -----------------------------------------------------

    def _dispatch(self, key: tuple[str, ...], cwd: Path | None) -> CommandOutcome:
        if key[:2] == ("npm", "view") and key[3:] == ("version",):
            return _ok(key, self._next_version(key[2].removesuffix("@latest")))
        if key[:3] == ("npm", "install", "-g"):
            package, _, version = key[3].partition("@")
            if package in self._refuse:
                return _fail(key, f"{package} install refused")
            self.installed[package] = version
            return _ok(key)
        if key == ("hallouminate", "--version"):
            version = self.installed.get("hallouminate")
            if version is None:
                return _fail(key, "hallouminate: command not found")
            return _ok(key, f"hallouminate {version}")
        if key[1:] == ("plugin", "marketplace", "add", MARKETPLACE_SOURCE):
            self.marketplaces.add(MARKETPLACE_SOURCE)
            return _ok(key)
        if key[1:] == ("plugin", "marketplace", "list", "--json"):
            return _ok(key, self._marketplace_listing())
        if len(key) == 4 and key[1] == "plugin" and key[2] in ("install", "add"):
            self.plugins.add(key[3])
            return _ok(key)
        if key[1:] == ("plugin", "list", "--json"):
            return _ok(key, self._plugin_listing())
        if key[:3] == ("hallouminate", "config", "init"):
            if "hallouminate-config" in self._refuse:
                return _fail(key, "config init refused")
            # The real CLI refuses to overwrite: `config init` on an existing
            # config exits 1 with "pass --force to overwrite". A fake that
            # always succeeds hides the one case where this step is reached
            # with a config already on disk.
            if self.config_exists and "--force" not in key:
                return _fail(
                    key,
                    f"config already exists at {self.home}/.config/hallouminate/config.toml;"
                    " pass --force to overwrite",
                )
            self.config_exists = True
            self.config_initialized = True
            return _ok(key)
        if key == ("hallouminate", "config", "validate"):
            return self._validate(key, cwd)
        if key[:2] == ("hallouminate", "init-repo"):
            self.initialized_repos.add(Path(key[3]))
            return _ok(key)
        if key[:2] == ("hallouminate", "index"):
            if cwd is not None:
                self.indexed_repos.add(cwd)
            return _ok(key)
        if key[:2] == ("hallouminate", "ground"):
            if cwd in self.indexed_repos:
                return _ok(key, '[{"path": ".hallouminate/wiki/index.md"}]')
            return _fail(key, "no corpus")
        if key[:4] == ("npx", "-y", "skills@latest", "add"):
            self.install_skills(_agent_of(key))
            return _ok(key)
        if key[:2] == ("sh", "-c"):
            expected_url = f"{RELEASE_URL}/tilth-{_target_triple()}.tar.gz"
            assert expected_url in key[2]
            self.installed["tilth"] = "nightly"
            return _ok(key)
        if len(key) == 2 and Path(key[0]).name == "tilth" and key[1] == "--version":
            if "tilth" not in self.installed:
                return _fail(key, "tilth: command not found")
            return _ok(key, "tilth 0.0.0-nightly")
        if len(key) == 4 and Path(key[0]).name == "tilth" and key[1] == "install":
            self.write_tilth_entry(key[2])
            return _ok(key)
        raise AssertionError(f"the fake world was asked to run an unmodelled command: {key}")

    def _marketplace_listing(self) -> str:
        """What `codex plugin marketplace list --json` prints.

        Codex answers ``{"marketplaces": [...]}`` with a nested
        ``marketplaceSource``, and always carries the same-named local decoy,
        which only the remote/local distinction keeps from satisfying the step.
        """
        entries: list[dict[str, object]] = [
            {
                "name": DECOY_MARKETPLACE,
                "marketplaceSource": {
                    "sourceType": "local",
                    "source": DECOY_MARKETPLACE_ROOT,
                },
            }
        ]
        entries += [
            {
                "name": MARKETPLACE_NAME,
                "marketplaceSource": {
                    "sourceType": "git",
                    "source": f"https://github.com/{source}.git",
                },
            }
            for source in sorted(self.marketplaces)
        ]
        return json.dumps({"marketplaces": entries})

    def _plugin_listing(self) -> str:
        """What `codex plugin list --json` prints.

        Codex lists what its marketplaces merely offer alongside what is
        installed, so an offered-but-uninstalled plugin appears with
        ``installed`` false — the exact row that must not satisfy the
        postcondition.
        """
        offered = sorted({PLUGIN_ID} - self.plugins) if self.marketplaces else []
        document = {
            "installed": [
                {"pluginId": plugin, "installed": True} for plugin in sorted(self.plugins)
            ],
            "available": [{"pluginId": plugin, "installed": False} for plugin in offered],
        }
        return json.dumps(document)

    def _validate(self, key: tuple[str, ...], cwd: Path | None) -> CommandOutcome:
        if cwd is None:
            if self.config_initialized:
                return _ok(key)
            return _fail(key, "no hallouminate config")
        if cwd in self.initialized_repos:
            return _ok(key, f"  - repo:{cwd.name}:wiki  → {cwd}/./.hallouminate/wiki")
        return _fail(key, f"{cwd} has no corpus")

    def _next_version(self, package: str) -> str:
        answers = self._versions.setdefault(package, ["1.0.0"])
        return answers.pop(0) if len(answers) > 1 else answers[0]


def _ok(argv: tuple[str, ...], stdout: str = "") -> CommandOutcome:
    return CommandOutcome(argv=argv, exit_code=0, stdout=stdout, stderr="", elapsed_ms=1)


def _fail(argv: tuple[str, ...], stderr: str) -> CommandOutcome:
    return CommandOutcome(argv=argv, exit_code=1, stdout="", stderr=stderr, elapsed_ms=1)


def _agent_of(key: tuple[str, ...]) -> str:
    return key[key.index("--agent") + 1]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw) if raw.strip() else {}


# ─── Fixtures and shared helpers ─────────────────────────────────────────────


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every filesystem root the installer touches into ``tmp_path``."""
    root = tmp_path / "home"
    root.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / ".config"))
    monkeypatch.setenv("PATH", str(empty_bin))
    monkeypatch.delenv("XDG_BIN_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return root


@pytest.fixture
def config_path(home: Path) -> Path:
    return home / ".config" / "cheese" / "config.toml"


def wire(monkeypatch: pytest.MonkeyPatch, world: FakeWorld) -> FakeWorld:
    """Fake only the CLI's child-process boundary; every module stays real."""
    monkeypatch.setattr(cli, "_default_runner", lambda env=None, *, timeout=None: world)
    return world


def manifest_text(
    *,
    harnesses: Sequence[str],
    components: Sequence[str],
    search_roots: Sequence[Path] = (),
    selected: Sequence[Path] = (),
    max_depth: int = 1,
) -> str:
    return (
        f"harnesses = {json.dumps(list(harnesses))}\n"
        f"components = {json.dumps(list(components))}\n"
        "\n[repositories]\n"
        f"search_roots = {json.dumps([str(p) for p in search_roots])}\n"
        f"max_depth = {max_depth}\n"
        f"selected = {json.dumps([str(p) for p in selected])}\n"
    )


def write_manifest(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def make_repository(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path.resolve()


def statuses(document: dict) -> list[tuple[str, str]]:
    return [(entry["step_id"], entry["status"]) for entry in document["results"]]


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ─── acceptance:145 — invalid manifests fail before anything happens ─────────


INVALID_MANIFESTS = [
    ("missing required component", 'harnesses = ["codex"]\ncomponents = ["hallouminate"]\n'),
    ("unknown harness", 'harnesses = ["pi"]\ncomponents = ["hallouminate", "easy-cheese"]\n'),
    ("unknown component", 'harnesses = ["codex"]\ncomponents = ["hallouminate", "omp"]\n'),
    ("unknown top-level key", 'harnesses = ["codex"]\ncomponents = []\nextra = 1\n'),
    ("unparseable toml", "harnesses = [\n"),
    ("no harnesses", 'harnesses = []\ncomponents = ["hallouminate", "easy-cheese"]\n'),
    (
        "relative search root",
        'harnesses = ["codex"]\ncomponents = ["hallouminate", "easy-cheese"]\n'
        '\n[repositories]\nsearch_roots = ["relative/path"]\n',
    ),
    (
        "selection outside the search roots",
        'harnesses = ["codex"]\ncomponents = ["hallouminate", "easy-cheese"]\n'
        '\n[repositories]\nsearch_roots = ["/srv/code"]\nselected = ["/elsewhere/repo"]\n',
    ),
]


@pytest.mark.parametrize(("name", "text"), INVALID_MANIFESTS)
@pytest.mark.parametrize("command", ["install", "doctor"])
def test_invalid_manifest_resolves_no_metadata_and_mutates_nothing(
    command: str,
    name: str,
    text: str,
    tmp_path: Path,
    home: Path,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = wire(monkeypatch, FakeWorld(home))
    manifest = write_manifest(tmp_path, text)

    result = cli_runner.invoke(app, [command, "--config", str(manifest)])

    assert result.exit_code == 2, f"{name}: manifest failures exit 2"
    assert world.calls == [], f"{name}: ran a command despite an invalid manifest"
    assert result.stdout == "", f"{name}: stdout must stay empty"
    assert str(manifest) in result.stderr
    assert snapshot(home) == {}, f"{name}: touched managed state"


def test_missing_manifest_resolves_no_metadata(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))

    result = cli_runner.invoke(app, ["install", "--config", str(tmp_path / "absent.toml")])

    assert result.exit_code == 2
    assert world.calls == []
    assert result.stdout == ""


# ─── acceptance:146 — cancelling before Apply writes no managed state ────────


def test_cancelling_the_wizard_writes_no_manifest_and_runs_nothing(
    home: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))

    result = cli_runner.invoke(app, ["install"], input="q\n")

    assert result.exit_code == 1
    assert world.calls == []
    assert result.stdout == ""
    assert not config_path.exists()
    assert snapshot(home) == {}


# ─── acceptance:147 — dry run emits the plan and changes nothing ─────────────


def test_dry_run_emits_the_exact_plan_without_executing_package_code(
    tmp_path: Path, home: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(harnesses=["codex"], components=["hallouminate", "easy-cheese", "tilth"]),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest), "--dry-run"])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["status"] == "succeeded"
    assert document["results"] == []
    assert [entry["step_id"] for entry in document["plan"]["steps"]] == [
        "hallouminate:npm-install",
        "hallouminate:marketplace:codex",
        "hallouminate:plugin:codex",
        "hallouminate:permission:codex",
        "hallouminate:config-init",
        "easy-cheese:install:codex",
        "tilth:install",
        "tilth:register:codex",
        "tilth:permission:codex",
    ]
    tilth_binary = str(_bin_dir() / "tilth")
    assert [entry["argv"] for entry in document["plan"]["steps"]] == [
        ["npm", "install", "-g", "hallouminate@1.0.0"],
        ["codex", "plugin", "marketplace", "add", MARKETPLACE_SOURCE],
        ["codex", "plugin", "add", PLUGIN_ID],
        [],
        ["hallouminate", "config", "init", "--force"],
        [
            "npx",
            "-y",
            "skills@latest",
            "add",
            EASY_CHEESE_SOURCE,
            "--skill",
            "*",
            "--agent",
            "codex",
            "--global",
            "--yes",
        ],
        ["sh", "-c", _install_script(_target_triple(), _bin_dir())],
        [tilth_binary, "install", "codex", "--edit"],
        [],
    ]
    # Metadata resolution is the only thing a dry run is allowed to do.
    assert world.argvs() == [
        ("npm", "view", "hallouminate@latest", "version"),
    ]
    assert snapshot(home) == {}
    assert not config_path.exists()


# ─── acceptance:148 + spec:125 — one JSON document on stdout ─────────────────


def test_complete_config_runs_headlessly_and_stdout_is_one_json_document(
    tmp_path: Path, home: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = make_repository(tmp_path / "code" / "alpha")
    world = wire(monkeypatch, FakeWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code", "cursor"],
            components=["hallouminate", "easy-cheese", "tilth"],
            search_roots=[(tmp_path / "code").resolve()],
            selected=[repository],
        ),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert result.stdout.strip() == json.dumps(document, indent=2)
    assert set(document) == {"status", "manifest", "plan", "results"}
    assert document["status"] == "succeeded"
    assert document["manifest"] == {
        "harnesses": ["claude-code", "cursor"],
        "components": ["hallouminate", "easy-cheese", "tilth"],
        "repositories": {
            "search_roots": [str((tmp_path / "code").resolve())],
            "max_depth": 1,
            "selected": [str(repository)],
        },
    }
    key = repository.as_posix()
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:marketplace:claude-code", "succeeded"),
        ("hallouminate:plugin:claude-code", "succeeded"),
        ("hallouminate:mcp:cursor", "succeeded"),
        ("hallouminate:permission:claude-code", "succeeded"),
        ("hallouminate:permission:cursor", "succeeded"),
        ("hallouminate:config-init", "succeeded"),
        (f"hallouminate:init-repo:{key}", "succeeded"),
        (f"hallouminate:index:{key}", "succeeded"),
        ("easy-cheese:install:claude-code", "succeeded"),
        # Cursor reads the same canonical skills store Claude Code's install
        # just filled, so its postcondition already holds and no second
        # `skills add` runs.
        ("easy-cheese:install:cursor", "skipped"),
        ("tilth:install", "succeeded"),
        ("tilth:register:claude-code", "succeeded"),
        ("tilth:register:cursor", "succeeded"),
        ("tilth:permission:claude-code", "succeeded"),
        ("tilth:permission:cursor", "succeeded"),
    ]
    # Every reported "succeeded" corresponds to a real mutation of the world.
    assert world.installed == {"hallouminate": "1.0.0", "tilth": "nightly"}
    assert world.initialized_repos == {repository}
    assert world.indexed_repos == {repository}
    assert "hallouminate:npm-install" in result.stderr
    assert not config_path.exists(), "headless install must not rewrite the default manifest"


# ─── acceptance:149 — a satisfied postcondition skips its mutation ───────────


def read_only_probes(home: Path) -> list[tuple[str, ...]]:
    """Every command a fully converged run may still run.

    easy-cheese contributes none: its postcondition reads the installed files
    directly, so a converged host needs no child process to prove the pack is
    there — and a host with no GitHub CLI reaches the same verdict. Claude
    Code registration contributes none either: it is declared in settings, so
    a host with no `claude` CLI reaches the same verdict too.
    """
    return [
        ("npm", "view", "hallouminate@latest", "version"),
        ("hallouminate", "--version"),
        ("codex", "plugin", "marketplace", "list", "--json"),
        ("codex", "plugin", "list", "--json"),
        ("hallouminate", "config", "validate"),
        (str(_bin_dir() / "tilth"), "--version"),
    ]


def test_already_satisfied_postconditions_skip_every_mutation(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))
    world.converge(harnesses=["claude-code", "codex"])
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code", "codex"],
            components=["hallouminate", "easy-cheese", "tilth"],
        ),
    )
    before = snapshot(home)

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert {status for _, status in statuses(document)} == {"skipped"}
    assert len(document["results"]) == 15
    assert world.argvs() == read_only_probes(home)
    assert snapshot(home) == before


# ─── acceptance:150 — one resolved version, planned and verified ─────────────


def test_apply_installs_exactly_the_version_planning_resolved(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for dropping ``adapters=`` from ``cli.apply_install_plan``.

    ``npm view`` answers 1.0.0 first and 9.9.9 forever after. If the CLI stops
    handing the planning adapters to apply, apply rebuilds them, re-resolves to
    9.9.9, and rejects the 1.0.0 it just installed — so both the call count and
    the step statuses below fail.
    """
    world = wire(
        monkeypatch,
        FakeWorld(
            home,
            versions={"hallouminate": ["1.0.0", "9.9.9"]},
        ),
    )
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code"], components=["hallouminate", "easy-cheese", "tilth"]
        ),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert world.count(("npm", "view", "hallouminate@latest", "version")) == 1
    planned = {entry["step_id"]: entry["argv"] for entry in document["plan"]["steps"]}
    assert planned["hallouminate:npm-install"] == ["npm", "install", "-g", "hallouminate@1.0.0"]
    assert planned["tilth:register:claude-code"] == [
        str(_bin_dir() / "tilth"),
        "install",
        "claude-code",
        "--edit",
    ]
    # The version the postcondition accepted is the version that got installed,
    # which is the version the plan declared.
    assert world.installed == {"hallouminate": "1.0.0", "tilth": "nightly"}
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:marketplace:claude-code", "succeeded"),
        ("hallouminate:plugin:claude-code", "succeeded"),
        ("hallouminate:permission:claude-code", "succeeded"),
        ("hallouminate:config-init", "succeeded"),
        ("easy-cheese:install:claude-code", "succeeded"),
        ("tilth:install", "succeeded"),
        ("tilth:register:claude-code", "succeeded"),
        ("tilth:permission:claude-code", "succeeded"),
    ]


def test_apply_cannot_be_called_without_the_planning_adapters(home: Path) -> None:
    """The unsafe call is not expressible: ``adapters`` is a required argument.

    Omitting it used to rebuild the adapters, re-run ``npm view``, and install a
    version the plan never showed. Now it cannot compile a call at all, so no
    caller can silently reintroduce a second resolution.
    """
    world = FakeWorld(home, versions={"hallouminate": ["1.0.0", "9.9.9"]})
    state = DesiredState(harnesses=("claude-code",), components=("hallouminate", "easy-cheese"))
    plan = build_install_plan(state, default_component_adapters(world))
    resolutions = world.count(("npm", "view", "hallouminate@latest", "version"))

    with pytest.raises(TypeError, match="adapters"):
        apply_install_plan(plan, world)  # type: ignore[call-arg]

    assert world.count(("npm", "view", "hallouminate@latest", "version")) == resolutions
    assert world.installed == {}


# ─── acceptance:151 — a failed step blocks its real dependents ───────────────


def test_failed_step_blocks_adapter_wired_dependents_and_lets_others_run(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = make_repository(tmp_path / "code" / "alpha")
    world = wire(
        monkeypatch,
        FakeWorld(home, refuse=frozenset({"hallouminate-config"})),
    )
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code"],
            components=["hallouminate", "easy-cheese", "tilth"],
            search_roots=[(tmp_path / "code").resolve()],
            selected=[repository],
        ),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["status"] == "failed"
    key = repository.as_posix()
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:marketplace:claude-code", "succeeded"),
        ("hallouminate:plugin:claude-code", "succeeded"),
        ("hallouminate:permission:claude-code", "succeeded"),
        ("hallouminate:config-init", "failed"),
        (f"hallouminate:init-repo:{key}", "blocked"),
        (f"hallouminate:index:{key}", "blocked"),
        ("easy-cheese:install:claude-code", "succeeded"),
        ("tilth:install", "succeeded"),
        ("tilth:register:claude-code", "succeeded"),
        ("tilth:permission:claude-code", "succeeded"),
    ]
    blocked = {entry["step_id"]: entry["remediation"] for entry in document["results"]}
    assert blocked[f"hallouminate:init-repo:{key}"] == (
        "blocked by unmet dependencies: hallouminate:config-init"
    )
    assert blocked[f"hallouminate:index:{key}"] == (
        f"blocked by unmet dependencies: hallouminate:init-repo:{key}"
    )
    assert ("hallouminate", "init-repo", "alpha", "--path", str(repository)) not in world.argvs()


# ─── acceptance:152 — interruption forwards, stops scheduling, reports ───────


def test_interrupt_forwards_the_signal_and_reports_the_remaining_steps(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(
        monkeypatch,
        FakeWorld(home, interrupt_on=("codex", "plugin", "marketplace", "add", MARKETPLACE_SOURCE)),
    )
    manifest = write_manifest(
        tmp_path,
        manifest_text(harnesses=["codex"], components=["hallouminate", "easy-cheese"]),
    )
    before = signal.getsignal(signal.SIGINT)

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["status"] == "interrupted"
    assert world.forwarded == [signal.SIGINT]
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:marketplace:codex", "succeeded"),
        ("hallouminate:plugin:codex", "interrupted"),
        ("hallouminate:permission:codex", "interrupted"),
        ("hallouminate:config-init", "interrupted"),
        ("easy-cheese:install:codex", "interrupted"),
    ]
    assert ("codex", "plugin", "add", PLUGIN_ID) not in world.argvs()
    assert signal.getsignal(signal.SIGINT) is before


# ─── acceptance:153 — doctor changes nothing ─────────────────────────────────


def test_doctor_runs_read_only_probes_and_leaves_every_file_byte_identical(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))
    world.converge(harnesses=["claude-code", "codex"])
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code", "codex"],
            components=["hallouminate", "easy-cheese", "tilth"],
        ),
    )
    before_home = snapshot(home)
    before_manifest = manifest.read_bytes()

    result = cli_runner.invoke(app, ["doctor", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert {status for _, status in statuses(document)} == {"succeeded"}
    assert world.argvs() == read_only_probes(home)
    assert snapshot(home) == before_home
    assert manifest.read_bytes() == before_manifest


def test_doctor_reports_every_unsatisfied_postcondition_independently(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = wire(monkeypatch, FakeWorld(home))
    world.installed["hallouminate"] = "1.0.0"
    manifest = write_manifest(
        tmp_path, manifest_text(harnesses=["codex"], components=["hallouminate", "easy-cheese"])
    )

    result = cli_runner.invoke(app, ["doctor", "--config", str(manifest)])

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:marketplace:codex", "failed"),
        ("hallouminate:plugin:codex", "failed"),
        ("hallouminate:permission:codex", "failed"),
        ("hallouminate:config-init", "failed"),
        ("easy-cheese:install:codex", "failed"),
    ]
    assert snapshot(home) == {}


# ─── A bare cloud box: no `gh`, no repository at the named path ──────────────


class GhlessWorld(FakeWorld):
    """A host where ``gh`` is not installed, exactly as a cloud box answers.

    Anything reaching for ``gh`` dies the way ``execvp`` does — exit 127 with
    the kernel's message — so a step that still depends on it cannot converge
    and cannot hide behind a modelled success.
    """

    def _dispatch(self, key: tuple[str, ...], cwd: Path | None) -> CommandOutcome:
        if key[0] == "gh":
            return CommandOutcome(
                argv=key,
                exit_code=127,
                stdout="",
                stderr="could not run gh: No such file or directory",
                elapsed_ms=1,
            )
        return super()._dispatch(key, cwd)


def test_install_converges_claude_code_without_the_claude_cli(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cloud regression: a Claude Cloud setup script runs with no `claude`
    on PATH, so registration never shells out to it — it is declared in user
    settings instead, and every step still converges."""
    world = wire(monkeypatch, FakeWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code"], components=["hallouminate", "easy-cheese", "tilth"]
        ),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["status"] == "succeeded"
    assert not any(argv[0] == "claude" for argv in world.argvs())
    settings = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["extraKnownMarketplaces"][MARKETPLACE_NAME] == {
        "source": {"source": "github", "repo": MARKETPLACE_SOURCE}
    }
    assert settings["enabledPlugins"] == {PLUGIN_ID: True}


def test_install_converges_every_easy_cheese_step_with_gh_absent(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure this whole change exists for: `gh` was an ambient prerequisite."""
    world = wire(monkeypatch, GhlessWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code", "codex", "cursor"],
            components=["hallouminate", "easy-cheese"],
        ),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    easy_cheese = [entry for entry in document["results"] if entry["component"] == "easy-cheese"]
    assert [entry["step_id"] for entry in easy_cheese] == [
        "easy-cheese:install:claude-code",
        "easy-cheese:install:codex",
        "easy-cheese:install:cursor",
    ]
    assert {entry["status"] for entry in easy_cheese} <= {"succeeded", "skipped"}
    assert not any(argv[0] == "gh" for argv in world.argvs())
    # The pack really is on disk for each harness, not merely reported so.
    for name in EASY_CHEESE_SKILLS:
        assert (home / CANONICAL_SKILLS_DIR / name / "SKILL.md").is_file()
        assert (home / CLAUDE_SKILLS_DIR / name / "SKILL.md").is_file()


@given("a cloud host without the GitHub CLI", target_fixture="cloud_install")
def cloud_install(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[GhlessWorld, Path]:
    world = wire(monkeypatch, GhlessWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(
            harnesses=["claude-code", "codex", "cursor"],
            components=["hallouminate", "easy-cheese"],
        ),
    )
    return world, manifest


@when("I install easy-cheese for every supported harness", target_fixture="install_document")
def install_easy_cheese(
    cloud_install: tuple[GhlessWorld, Path],
) -> tuple[GhlessWorld, dict[str, object]]:
    world, manifest = cloud_install
    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    return world, json.loads(result.stdout)


@then("easy-cheese is installed for every supported harness")
def easy_cheese_is_installed(install_document: tuple[GhlessWorld, dict[str, object]]) -> None:
    _world, document = install_document
    easy_cheese = [entry for entry in document["results"] if entry["component"] == "easy-cheese"]

    assert [entry["step_id"] for entry in easy_cheese] == [
        "easy-cheese:install:claude-code",
        "easy-cheese:install:codex",
        "easy-cheese:install:cursor",
    ]
    assert {entry["status"] for entry in easy_cheese} <= {"succeeded", "skipped"}


@then("no command uses the GitHub CLI")
def no_github_cli_command_runs(install_document: tuple[GhlessWorld, dict[str, object]]) -> None:
    world, _document = install_document

    assert not any(argv[0] == "gh" for argv in world.argvs())


def test_install_repairs_a_config_that_exists_but_does_not_validate(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken config must not leave an install that fails the same way forever.

    The configure step runs only when `config validate` fails, and the real CLI
    refuses to overwrite without `--force` — so planning it unforced turns a
    stale config into a permanently stuck install whose error names a flag the
    user cannot supply.
    """
    world = wire(monkeypatch, FakeWorld(home))
    # On disk but not valid: exactly the state that reaches the mutation.
    world.config_exists = True
    manifest = write_manifest(
        tmp_path,
        manifest_text(harnesses=["claude-code"], components=["hallouminate", "easy-cheese"]),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    config_step = next(
        entry for entry in document["results"] if entry["step_id"] == "hallouminate:config-init"
    )
    assert config_step["status"] == "succeeded", config_step.get("stderr_tail")
    assert world.config_initialized


def test_a_repo_option_that_is_not_a_repository_exits_two_before_planning(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """acceptance:25 — a stranger path fails at parse time, not as a blocked step mid-apply."""
    stranger = tmp_path / "not-a-repository"
    stranger.mkdir()
    world = wire(monkeypatch, FakeWorld(home))

    result = cli_runner.invoke(
        app, ["install", "--harness", "claude-code", "--repo", str(stranger)]
    )

    assert result.exit_code == 2
    assert str(stranger) in result.stderr
    assert result.stdout == "", "nothing was planned, so there is no report to emit"
    assert world.calls == []
    assert snapshot(home) == {}


# ─── acceptance:154 — discovered repositories start unchecked ────────────────


def test_wizard_lists_deduplicated_canonical_candidates_all_unchecked(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = (tmp_path / "code").resolve()
    alpha = make_repository(root / "alpha")
    nested_alpha = make_repository(root / "nested" / "alpha")
    linked = root / "linked"
    linked.mkdir()
    (linked / ".git").write_text(f"gitdir: {alpha / '.git' / 'worktrees' / 'linked'}\n")
    (alpha / ".git" / "worktrees" / "linked").mkdir(parents=True)
    (alpha / ".git" / "worktrees" / "linked" / "commondir").write_text("../..\n")
    monkeypatch.setattr(sys, "stdin", _stdin(["", "1", "", "", str(root), "2", "", ""]))

    state = run_wizard(None)

    assert state is not None
    assert state.repositories.selected == ()
    assert state.repositories.search_roots == (root,)
    assert state.repositories.max_depth == 2
    # Every discovered repository, canonicalized, deduplicated, and unchecked.
    listing = "".join(
        f"  {number}. [ ] {path}\n" for number, path in enumerate([alpha, linked, nested_alpha], 1)
    )
    assert listing in capsys.readouterr().err


# ─── acceptance:155 — drift after Preview blocks only that repository ────────


def test_repository_drift_after_planning_blocks_only_that_repository(
    tmp_path: Path, home: Path
) -> None:
    root = (tmp_path / "code").resolve()
    drifted = make_repository(root / "drifted")
    healthy = make_repository(root / "healthy")
    world = FakeWorld(home)
    state = DesiredState(
        harnesses=("claude-code",),
        components=("hallouminate", "easy-cheese"),
        repositories={"search_roots": (root,), "max_depth": 1, "selected": (drifted, healthy)},
    )
    adapters = default_component_adapters(world)
    plan = build_install_plan(state, adapters)

    (drifted / ".git").rmdir()
    report = apply_install_plan(plan, world, adapters=adapters)

    results = {result.step_id: result.status for result in report.results}
    assert results[f"hallouminate:init-repo:{drifted.as_posix()}"] is StepStatus.BLOCKED
    assert results[f"hallouminate:index:{drifted.as_posix()}"] is StepStatus.BLOCKED
    assert results[f"hallouminate:init-repo:{healthy.as_posix()}"] is StepStatus.SUCCEEDED
    assert results[f"hallouminate:index:{healthy.as_posix()}"] is StepStatus.SUCCEEDED
    assert results["easy-cheese:install:claude-code"] is StepStatus.SUCCEEDED
    assert world.initialized_repos == {healthy}


# ─── acceptance:156 — Cursor gets MCP entries, not plugin workflows ──────────


def test_cursor_selection_writes_both_mcp_entries_and_preserves_the_rest(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cursor_config = home / CURSOR_MCP_CONFIG
    cursor_config.parent.mkdir(parents=True)
    cursor_config.write_text(
        json.dumps(
            {
                "someOtherSetting": {"keep": True},
                "mcpServers": {"unrelated": {"command": "unrelated-server"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    cursor_cli_config = home / ".cursor/cli-config.json"
    cursor_cli_config.write_text(
        json.dumps({"permissions": {"allow": ["Shell(ls)"]}, "keep": True}),
        encoding="utf-8",
    )
    world = wire(monkeypatch, FakeWorld(home))
    manifest = write_manifest(
        tmp_path,
        manifest_text(harnesses=["cursor"], components=["hallouminate", "easy-cheese", "tilth"]),
    )

    result = cli_runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert statuses(document) == [
        ("hallouminate:npm-install", "succeeded"),
        ("hallouminate:mcp:cursor", "succeeded"),
        ("hallouminate:permission:cursor", "succeeded"),
        ("hallouminate:config-init", "succeeded"),
        ("easy-cheese:install:cursor", "succeeded"),
        ("tilth:install", "succeeded"),
        ("tilth:register:cursor", "succeeded"),
        ("tilth:permission:cursor", "succeeded"),
    ]
    assert json.loads(cursor_config.read_text(encoding="utf-8")) == {
        "someOtherSetting": {"keep": True},
        "mcpServers": {
            "unrelated": {"command": "unrelated-server"},
            "hallouminate": HALLOUMINATE_CURSOR_ENTRY,
            "tilth": tilth_entry(),
        },
    }
    assert json.loads(cursor_cli_config.read_text(encoding="utf-8")) == {
        "permissions": {"allow": ["Shell(ls)", "Mcp(hallouminate:*)", "Mcp(tilth:*)"]},
        "keep": True,
    }
    assert not any(argv[:2] == ("cursor", "plugin") for argv in world.argvs())


# ─── acceptance:157 — the v1 package carries none of the v0 surface ──────────


PURGED_MODULES = (
    "cheese_flow.mcp_server",
    "cheese_flow.lib",
    "cheese_flow.lib.compiler",
    "cheese_flow.lib.installer",
    "cheese_flow.lib.session_start",
    "cheese_flow.adapters.copilot_cli",
)


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def test_built_package_declares_no_milknado_dependency_or_extra_entry_point() -> None:
    document = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]
    names = sorted(
        requirement.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
        for requirement in project["dependencies"]
    )

    assert names == ["PyYAML", "cyclopts", "pydantic", "rich", "tomlkit"]
    assert project["scripts"] == {"cheese": "cheese_flow.cli:app"}
    assert "entry-points" not in project
    assert "optional-dependencies" not in project


def test_importable_surface_holds_no_compiler_milknado_or_unified_mcp_module() -> None:
    assert [name for name in PURGED_MODULES if _importable(name)] == []


def test_cli_exposes_exactly_install_doctor_and_profile() -> None:
    exposed = [name for name in app if not name.startswith("-")]

    assert sorted(exposed) == ["doctor", "install", "profile"]


# ─── Round trip: wizard → save → load → plan → apply ─────────────────────────


def _stdin(lines: list[str]) -> io.StringIO:
    return io.StringIO("".join(f"{line}\n" for line in lines))


def test_wizard_state_round_trips_through_disk_to_an_identical_plan(
    tmp_path: Path, home: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "code").resolve()
    repository = make_repository(root / "alpha")
    monkeypatch.setattr(sys, "stdin", _stdin(["", "1 3", "", "", str(root), "1", "1", "", ""]))

    accepted = run_wizard(None)

    assert accepted == DesiredState(
        harnesses=("claude-code", "cursor"),
        components=("hallouminate", "easy-cheese"),
        repositories={"search_roots": (root,), "max_depth": 1, "selected": (repository,)},
    )

    save_desired_state(accepted, config_path)
    loaded = load_desired_state(config_path)
    assert loaded == accepted

    planning_world = FakeWorld(home)
    direct = build_install_plan(accepted, default_component_adapters(planning_world))
    apply_world = FakeWorld(home)
    adapters = default_component_adapters(apply_world)
    from_disk = build_install_plan(loaded, adapters)

    assert from_disk == direct

    report = apply_install_plan(from_disk, apply_world, adapters=adapters)

    # Cursor's easy-cheese step is the one exception: Claude Code's install
    # already filled the canonical skills store Cursor reads, so it converges
    # without running.
    reached = {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
    assert {result.status for result in report.results} <= reached
    assert [result.step_id for result in report.results if result.status is StepStatus.SKIPPED] == [
        "easy-cheese:install:cursor"
    ]
    assert apply_world.initialized_repos == {repository}


def test_wizard_state_round_trips_through_a_symlinked_search_root(
    tmp_path: Path, home: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlinked search root must not produce a manifest the tool cannot read.

    The wizard canonicalizes candidates but takes the root as typed, so an
    unresolved root plus a resolved selection used to fail the loader's own
    consistency check and brick both ``install`` and ``doctor``.
    """
    real = (tmp_path / "data" / "code").resolve()
    real.mkdir(parents=True)
    link = tmp_path / "code"
    link.symlink_to(real)
    repository = make_repository(real / "alpha")
    monkeypatch.setattr(sys, "stdin", _stdin(["", "1", "", "", str(link), "1", "1", "", ""]))

    accepted = run_wizard(None)

    assert accepted is not None
    assert accepted.repositories.search_roots == (real,)
    assert accepted.repositories.selected == (repository,)

    save_desired_state(accepted, config_path)
    loaded = load_desired_state(config_path)
    assert loaded == accepted

    world = FakeWorld(home)
    adapters = default_component_adapters(world)
    plan = build_install_plan(loaded, adapters)

    report = apply_install_plan(plan, world, adapters=adapters)

    assert [result.status for result in report.results] == [StepStatus.SUCCEEDED] * len(plan.steps)
    assert world.initialized_repos == {repository}
