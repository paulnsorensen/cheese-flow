"""Adapter contract tests: exact argv, once-per-run version resolution, and
positive postconditions driven entirely through a scripted fake ``CommandRunner``."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import stat as stat_mod
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from cheese_flow.adapters import (
    EasyCheeseAdapter,
    HallouminateAdapter,
    TilthAdapter,
    default_component_adapters,
    easy_cheese,
)
from cheese_flow.adapters.easy_cheese import AGENT_TOKENS, CORE_SKILLS, skills_directory
from cheese_flow.adapters.hallouminate import _owner_repo
from cheese_flow.adapters.tilth import (
    RELEASE_URL,
    _bin_dir,
    _install_script,
    _launches_tilth,
    _target_triple,
)
from cheese_flow.models import (
    CommandOutcome,
    ConfigEdit,
    DesiredState,
    Phase,
    PlanStep,
    RepositorySelection,
    StepResult,
    StepStatus,
)
from pydantic import ValidationError

ALL_HARNESSES = ("claude-code", "codex", "cursor")


class FakeRunner:
    """Records every argv and replays scripted outcomes keyed by exact argv."""

    def __init__(self, script: dict[tuple[str, ...], CommandOutcome] | None = None) -> None:
        self.script = dict(script or {})
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        key = tuple(argv)
        self.calls.append((key, cwd))
        if key in self.script:
            return self.script[key]
        return CommandOutcome(argv=key, exit_code=127, stdout="", stderr="unscripted", elapsed_ms=0)

    def argvs(self) -> list[tuple[str, ...]]:
        return [argv for argv, _ in self.calls]


def outcome(argv: tuple[str, ...], *, exit_code: int = 0, stdout: str = "") -> CommandOutcome:
    return CommandOutcome(argv=argv, exit_code=exit_code, stdout=stdout, stderr="", elapsed_ms=1)


NPM_VIEW_HALLOUMINATE = ("npm", "view", "hallouminate@latest", "version")

HALLOUMINATE_VERSION = "0.42.1"


def npm_script() -> dict[tuple[str, ...], CommandOutcome]:
    return {
        NPM_VIEW_HALLOUMINATE: outcome(NPM_VIEW_HALLOUMINATE, stdout=f"{HALLOUMINATE_VERSION}\n"),
    }


def state(
    *,
    harnesses: tuple[str, ...] = ALL_HARNESSES,
    components: tuple[str, ...] = ("hallouminate", "easy-cheese", "tilth"),
    selected: tuple[Path, ...] = (),
    search_roots: tuple[Path, ...] = (Path("/repos"),),
) -> DesiredState:
    return DesiredState(
        harnesses=harnesses,
        components=components,
        repositories=RepositorySelection(search_roots=search_roots, selected=selected),
    )


def steps_by_id(steps: Sequence[PlanStep]) -> dict[str, PlanStep]:
    return {step.step_id: step for step in steps}


# --------------------------------------------------------------------------
# Hallouminate — planning
# --------------------------------------------------------------------------


def test_hallouminate_plans_versioned_global_npm_install() -> None:
    runner = FakeRunner(npm_script())
    steps = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))

    install = steps["hallouminate:npm-install"]
    assert install.argv == ("npm", "install", "-g", f"hallouminate@{HALLOUMINATE_VERSION}")
    assert install.phase is Phase.INSTALL
    assert install.depends_on == ()


def test_hallouminate_plugin_argv_per_native_harness() -> None:
    runner = FakeRunner(npm_script())
    steps = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))

    assert steps["hallouminate:marketplace:claude-code"].argv == (
        "claude",
        "plugin",
        "marketplace",
        "add",
        "paulnsorensen/hallouminate",
    )
    assert steps["hallouminate:plugin:claude-code"].argv == (
        "claude",
        "plugin",
        "install",
        "hallouminate@hallouminate",
    )
    assert steps["hallouminate:marketplace:codex"].argv == (
        "codex",
        "plugin",
        "marketplace",
        "add",
        "paulnsorensen/hallouminate",
    )
    assert steps["hallouminate:plugin:codex"].argv == (
        "codex",
        "plugin",
        "add",
        "hallouminate@hallouminate",
    )


def test_hallouminate_gives_cursor_no_plugin_steps() -> None:
    runner = FakeRunner(npm_script())
    steps = HallouminateAdapter(runner).plan_steps(state())

    assert "hallouminate:plugin:cursor" not in steps_by_id(steps)
    assert "hallouminate:marketplace:cursor" not in steps_by_id(steps)
    assert [s.step_id for s in steps if s.harness == "cursor"] == [
        "hallouminate:mcp:cursor",
        "hallouminate:permission:cursor",
    ]


def test_hallouminate_registers_cursor_mcp_entry_declaratively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = FakeRunner(npm_script())
    step = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))["hallouminate:mcp:cursor"]

    assert step.harness == "cursor"
    assert step.phase is Phase.REGISTER
    assert step.argv == ()
    assert step.depends_on == ("hallouminate:npm-install",)
    assert step.config_edit == ConfigEdit(
        target=tmp_path / ".cursor/mcp.json",
        pointer="mcpServers.hallouminate",
        value={"command": "hallouminate", "args": ["serve"]},
    )


def test_hallouminate_plans_native_mcp_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_home = tmp_path / "claude"
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    steps = steps_by_id(HallouminateAdapter(FakeRunner(npm_script())).plan_steps(state()))

    expected = {
        "claude-code": (
            "hallouminate:plugin:claude-code",
            ConfigEdit(
                target=claude_home / "settings.json",
                pointer="permissions.allow",
                value="mcp__plugin_hallouminate_hallouminate__*",
                mode="append_unique",
            ),
        ),
        "codex": (
            "hallouminate:plugin:codex",
            ConfigEdit(
                target=codex_home / "config.toml",
                pointer=(
                    "plugins.hallouminate.mcp_servers.hallouminate.default_tools_approval_mode"
                ),
                value="approve",
                mode="toml_set",
            ),
        ),
        "cursor": (
            "hallouminate:mcp:cursor",
            ConfigEdit(
                target=tmp_path / ".cursor/cli-config.json",
                pointer="permissions.allow",
                value="Mcp(hallouminate:*)",
                mode="append_unique",
            ),
        ),
    }
    for harness, (dependency, edit) in expected.items():
        permission = steps[f"hallouminate:permission:{harness}"]
        assert permission.depends_on == (dependency,)
        assert permission.config_edit == edit
        assert "configures" in permission.postcondition


def test_hallouminate_permission_postconditions_require_each_native_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    permissions = {
        harness: steps_by_id(adapter.plan_steps(state()))[f"hallouminate:permission:{harness}"]
        for harness in ALL_HARNESSES
    }

    assert all(
        adapter.check_postcondition(permission, FakeRunner()) is False
        for permission in permissions.values()
    )

    claude = tmp_path / ".claude/settings.json"
    claude.parent.mkdir()
    claude.write_text(
        json.dumps({"permissions": {"allow": ["mcp__plugin_hallouminate_hallouminate__*"]}}),
        encoding="utf-8",
    )
    codex = tmp_path / ".codex/config.toml"
    codex.parent.mkdir()
    codex.write_text(
        "[plugins.hallouminate.mcp_servers.hallouminate]\n"
        'default_tools_approval_mode = "approve"\n',
        encoding="utf-8",
    )
    cursor = tmp_path / ".cursor/cli-config.json"
    cursor.parent.mkdir()
    cursor.write_text(
        json.dumps({"permissions": {"allow": ["Mcp(hallouminate:*)"]}}),
        encoding="utf-8",
    )

    assert all(
        adapter.check_postcondition(permission, FakeRunner()) is True
        for permission in permissions.values()
    )


def test_hallouminate_omits_the_cursor_mcp_step_when_cursor_is_not_selected() -> None:
    runner = FakeRunner(npm_script())
    steps = HallouminateAdapter(runner).plan_steps(state(harnesses=("claude-code", "codex")))

    assert "hallouminate:mcp:cursor" not in steps_by_id(steps)


def test_hallouminate_config_init_forces_and_depends_on_install() -> None:
    """The step runs only when validation already failed, so overwriting is the fix.

    Real `hallouminate config init` exits 1 on an existing config with "pass
    --force to overwrite". Planning it without the flag leaves anyone whose
    config is present but invalid with an install that fails the same way on
    every retry, citing a flag they cannot supply.
    """
    runner = FakeRunner(npm_script())
    config = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))[
        "hallouminate:config-init"
    ]

    assert config.argv == ("hallouminate", "config", "init", "--force")
    assert config.phase is Phase.CONFIGURE
    assert config.depends_on == ("hallouminate:npm-install",)


def test_hallouminate_registration_depends_on_install_and_plugin_on_marketplace() -> None:
    runner = FakeRunner(npm_script())
    steps = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))

    assert steps["hallouminate:marketplace:codex"].depends_on == ("hallouminate:npm-install",)
    assert steps["hallouminate:plugin:codex"].depends_on == ("hallouminate:marketplace:codex",)


def test_hallouminate_emits_independent_steps_per_selected_repository() -> None:
    runner = FakeRunner(npm_script())
    repos = (Path("/repos/alpha"), Path("/repos/beta"))
    steps = steps_by_id(HallouminateAdapter(runner).plan_steps(state(selected=repos)))

    init = steps["hallouminate:init-repo:/repos/alpha"]
    assert init.argv == (
        "hallouminate",
        "init-repo",
        "--path",
        "/repos/alpha",
        "--",
        "alpha",
    )
    assert init.phase is Phase.INITIALIZE
    assert init.repository == Path("/repos/alpha")
    assert init.depends_on == ("hallouminate:config-init",)

    index = steps["hallouminate:index:/repos/beta"]
    assert index.argv == (
        "hallouminate",
        "index",
        "--corpus",
        "repo:beta:wiki",
        "--strict",
    )
    assert index.depends_on == ("hallouminate:init-repo:/repos/beta",)


def test_hallouminate_init_repo_argv_isolates_a_dash_prefixed_repository_name() -> None:
    # H4: a bare positional ahead of flags lets a directory literally named
    # `--corpus` be parsed as an option by the child CLI.
    runner = FakeRunner(npm_script())
    repo = Path("/repos/--corpus")
    steps = steps_by_id(HallouminateAdapter(runner).plan_steps(state(selected=(repo,))))

    argv = steps[f"hallouminate:init-repo:{repo.as_posix()}"].argv
    assert argv == ("hallouminate", "init-repo", "--path", "/repos/--corpus", "--", "--corpus")


def test_hallouminate_emits_no_repository_steps_when_selection_is_empty() -> None:
    runner = FakeRunner(npm_script())
    steps = HallouminateAdapter(runner).plan_steps(state(selected=()))

    assert [s.step_id for s in steps if s.phase is Phase.INITIALIZE] == []


def test_hallouminate_resolves_npm_view_once_per_run() -> None:
    runner = FakeRunner(npm_script())
    adapter = HallouminateAdapter(runner)
    adapter.plan_steps(state(selected=(Path("/repos/alpha"), Path("/repos/beta"))))
    adapter.plan_steps(state())
    adapter.check_postcondition(
        PlanStep(
            step_id="hallouminate:npm-install",
            component="hallouminate",
            phase=Phase.INSTALL,
            argv=("npm", "install", "-g", "hallouminate@0.42.1"),
            postcondition="x",
        ),
        runner,
    )

    assert runner.argvs().count(NPM_VIEW_HALLOUMINATE) == 1


def test_hallouminate_raises_when_npm_view_fails() -> None:
    runner = FakeRunner({NPM_VIEW_HALLOUMINATE: outcome(NPM_VIEW_HALLOUMINATE, exit_code=1)})
    with pytest.raises(RuntimeError, match="hallouminate@latest"):
        HallouminateAdapter(runner).plan_steps(state())


# --------------------------------------------------------------------------
# Hallouminate — postconditions
# --------------------------------------------------------------------------


def hallouminate_steps(
    runner: FakeRunner,
    repos: tuple[Path, ...] = (),
    search_roots: tuple[Path, ...] = (Path("/repos"),),
) -> dict[str, PlanStep]:
    return steps_by_id(
        HallouminateAdapter(runner).plan_steps(state(selected=repos, search_roots=search_roots))
    )


def test_hallouminate_install_postcondition_requires_the_resolved_version() -> None:
    planner = FakeRunner(npm_script())
    adapter = HallouminateAdapter(planner)
    step = steps_by_id(adapter.plan_steps(state()))["hallouminate:npm-install"]

    version_argv = ("hallouminate", "--version")
    satisfied = FakeRunner(
        {version_argv: outcome(version_argv, stdout=f"hallouminate {HALLOUMINATE_VERSION}\n")}
    )
    assert adapter.check_postcondition(step, satisfied) is True
    assert satisfied.argvs() == [version_argv]

    # Exit 0 but the installed executable is an older release: not converged.
    stale = FakeRunner({version_argv: outcome(version_argv, stdout="hallouminate 0.1.0\n")})
    assert adapter.check_postcondition(step, stale) is False


# Verbatim shapes from the real CLIs (`plugin marketplace list --json`).
CODEX_MARKETPLACE_JSON = json.dumps(
    {
        "marketplaces": [
            {
                "name": "hallouminate",
                "root": "/home/paul/.cache/ap/plugins/hallouminate",
                "marketplaceSource": {
                    "sourceType": "git",
                    "source": "https://github.com/paulnsorensen/hallouminate.git",
                },
            }
        ]
    }
)
# The live state on a developer machine: the name matches, the source does not.
CODEX_MARKETPLACE_JSON_LOCAL = json.dumps(
    {
        "marketplaces": [
            {
                "name": "hallouminate",
                "root": "/home/paul/.cache/ap/plugins/hallouminate",
                "marketplaceSource": {
                    "sourceType": "local",
                    "source": "/home/paul/.cache/ap/plugins/hallouminate",
                },
            },
            {
                "name": "claude-code-plugins",
                "root": "/home/paul/.codex/.tmp/marketplaces/claude-code-plugins",
                "marketplaceSource": {
                    "sourceType": "git",
                    "source": "https://github.com/anthropics/claude-code.git",
                },
            },
        ]
    }
)
CLAUDE_MARKETPLACE_JSON = json.dumps(
    [
        {
            "name": "hallouminate",
            "source": "github",
            "repo": "paulnsorensen/hallouminate",
            "installLocation": "/home/paul/.claude/plugins/marketplaces/hallouminate",
        }
    ]
)
CLAUDE_MARKETPLACE_JSON_DIRECTORY = json.dumps(
    [
        {
            "name": "hallouminate",
            "source": "directory",
            "path": "/home/paul/.cache/ap/plugins/hallouminate",
            "installLocation": "/home/paul/.cache/ap/plugins/hallouminate",
        },
        {
            "name": "claude-plugins-official",
            "source": "github",
            "repo": "anthropics/claude-plugins-official",
            "installLocation": "/home/paul/.claude/plugins/marketplaces/official",
        },
    ]
)


def test_hallouminate_marketplace_postcondition_reads_the_native_listing() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:marketplace:codex"]

    list_argv = ("codex", "plugin", "marketplace", "list", "--json")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CODEX_MARKETPLACE_JSON)})
    assert adapter.check_postcondition(step, ok) is True
    assert ok.argvs() == [list_argv]

    empty = FakeRunner({list_argv: outcome(list_argv, stdout='{"marketplaces": []}')})
    assert adapter.check_postcondition(step, empty) is False

    garbage = FakeRunner({list_argv: outcome(list_argv, stdout="not json")})
    assert adapter.check_postcondition(step, garbage) is False


def test_hallouminate_marketplace_postcondition_reads_the_claude_listing() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:marketplace:claude-code"]

    list_argv = ("claude", "plugin", "marketplace", "list", "--json")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CLAUDE_MARKETPLACE_JSON)})
    assert adapter.check_postcondition(step, ok) is True
    assert ok.argvs() == [list_argv]


def test_hallouminate_marketplace_postcondition_rejects_a_same_named_local_marketplace() -> None:
    # H-A2: `hallouminate` is already registered on developer machines from a
    # local directory. The name matches; `paulnsorensen/hallouminate` was never
    # added, so the step must still run rather than resolve against a stranger.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    steps = hallouminate_steps(FakeRunner(npm_script()))

    codex_argv = ("codex", "plugin", "marketplace", "list", "--json")
    codex = FakeRunner({codex_argv: outcome(codex_argv, stdout=CODEX_MARKETPLACE_JSON_LOCAL)})
    assert adapter.check_postcondition(steps["hallouminate:marketplace:codex"], codex) is False

    claude_argv = ("claude", "plugin", "marketplace", "list", "--json")
    claude = FakeRunner(
        {claude_argv: outcome(claude_argv, stdout=CLAUDE_MARKETPLACE_JSON_DIRECTORY)}
    )
    step = steps["hallouminate:marketplace:claude-code"]
    assert adapter.check_postcondition(step, claude) is False


def test_hallouminate_marketplace_postcondition_names_the_json_listing() -> None:
    steps = hallouminate_steps(FakeRunner(npm_script()))
    assert steps["hallouminate:marketplace:codex"].postcondition == (
        "`codex plugin marketplace list --json` reports paulnsorensen/hallouminate"
    )


def test_owner_repo_normalizes_scp_https_and_git_suffix_forms() -> None:
    # H2: SCP-style remotes split only on ":", so the marketplace postcondition
    # can never converge for a repo cloned via `git@github.com:owner/repo.git`.
    assert _owner_repo("git@github.com:owner/repo.git") == "owner/repo"
    assert _owner_repo("https://github.com/owner/repo.git") == "owner/repo"
    assert _owner_repo("https://github.com/owner/repo") == "owner/repo"


# Verbatim `claude plugin list --json` rows. Every plugin on a real machine
# reports `enabled: false`, so the check reads `scope` and never `enabled`.
CLAUDE_PLUGIN_LIST_JSON = json.dumps(
    [
        {
            "id": "hallouminate@hallouminate",
            "version": "0.3.2",
            "scope": "user",
            "enabled": False,
            "installPath": "/home/paul/.claude/plugins/cache/hallouminate/hallouminate/0.3.2",
        }
    ]
)
# `claude plugin list` reports OTHER projects' project-scoped plugins globally.
CLAUDE_PLUGIN_LIST_JSON_FOREIGN_PROJECT = json.dumps(
    [
        {
            "id": "hallouminate@hallouminate",
            "version": "ad8a4253ce7d",
            "scope": "project",
            "enabled": False,
            "installPath": "/home/paul/.claude/plugins/cache/hallouminate/hallouminate/ad8a",
            "projectPath": "/home/paul/Dev/easy-cheese/.worktrees/dogfood",
        }
    ]
)
CODEX_PLUGIN_LIST_JSON = json.dumps(
    {
        "installed": [
            {
                "pluginId": "hallouminate@hallouminate",
                "marketplaceName": "hallouminate",
                "version": "0.3.2",
                "installed": True,
                "enabled": True,
            }
        ],
        "available": [],
    }
)
CODEX_PLUGIN_LIST_JSON_AVAILABLE_ONLY = json.dumps(
    {
        "installed": [],
        "available": [
            {
                "pluginId": "hallouminate@hallouminate",
                "marketplaceName": "hallouminate",
                "installed": False,
                "enabled": False,
            }
        ],
    }
)
# `codex plugin list` (no --json) prints available-but-uninstalled rows too.
CODEX_PLUGIN_LIST_PLAIN = (
    "PLUGIN                             STATUS              VERSION\n"
    "agent-sdk-dev@claude-code-plugins  not installed\n"
    "hallouminate@hallouminate          not installed\n"
)


def test_hallouminate_plugin_postcondition_requires_the_plugin_id() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:claude-code"]

    # `claude plugin list --json` returns a flat list keyed `id`.
    list_argv = ("claude", "plugin", "list", "--json")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CLAUDE_PLUGIN_LIST_JSON)})
    assert adapter.check_postcondition(step, ok) is True
    assert ok.argvs() == [list_argv]

    # `claude plugin list` exits 0 with nothing installed.
    empty = FakeRunner({list_argv: outcome(list_argv, stdout="[]")})
    assert adapter.check_postcondition(step, empty) is False

    garbage = FakeRunner({list_argv: outcome(list_argv, stdout="not json")})
    assert adapter.check_postcondition(step, garbage) is False


def test_hallouminate_plugin_postcondition_rejects_another_projects_plugin() -> None:
    # H-A1: `claude plugin list` reports project-scoped plugins belonging to
    # unrelated checkouts. A user-scope registration is not satisfied by one.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:claude-code"]

    list_argv = ("claude", "plugin", "list", "--json")
    foreign = FakeRunner(
        {list_argv: outcome(list_argv, stdout=CLAUDE_PLUGIN_LIST_JSON_FOREIGN_PROJECT)}
    )
    assert adapter.check_postcondition(step, foreign) is False


def test_hallouminate_plugin_postcondition_ignores_the_enabled_flag() -> None:
    # Every plugin claude reports carries `enabled: false`, including active
    # ones, so the flag must never veto an otherwise user-scoped registration.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:claude-code"]

    list_argv = ("claude", "plugin", "list", "--json")
    document = json.dumps([{"id": "hallouminate@hallouminate", "scope": "user", "enabled": False}])
    runner = FakeRunner({list_argv: outcome(list_argv, stdout=document)})
    assert adapter.check_postcondition(step, runner) is True


def test_hallouminate_plugin_postcondition_reads_the_codex_installed_section() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:codex"]

    list_argv = ("codex", "plugin", "list", "--json")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CODEX_PLUGIN_LIST_JSON)})
    assert adapter.check_postcondition(step, ok) is True
    assert ok.argvs() == [list_argv]


def test_hallouminate_plugin_postcondition_rejects_a_merely_available_codex_plugin() -> None:
    # B1: `codex plugin list` lists plugins offered by every marketplace, so the
    # plugin id appears in the plain listing before it is ever installed. Both
    # listings are scripted: only reading the `installed` section rejects this.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:codex"]

    plain = ("codex", "plugin", "list")
    as_json = ("codex", "plugin", "list", "--json")
    available = FakeRunner(
        {
            plain: outcome(plain, stdout=CODEX_PLUGIN_LIST_PLAIN),
            as_json: outcome(as_json, stdout=CODEX_PLUGIN_LIST_JSON_AVAILABLE_ONLY),
        }
    )
    assert adapter.check_postcondition(step, available) is False
    assert available.argvs() == [as_json]


def test_hallouminate_plugin_postcondition_rejects_an_entry_flagged_not_installed() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:codex"]

    as_json = ("codex", "plugin", "list", "--json")
    document = json.dumps(
        {"installed": [{"pluginId": "hallouminate@hallouminate", "installed": False}]}
    )
    runner = FakeRunner({as_json: outcome(as_json, stdout=document)})
    assert adapter.check_postcondition(step, runner) is False


def test_hallouminate_plugin_postcondition_names_the_json_listing() -> None:
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:plugin:codex"]
    assert step.postcondition == (
        "`codex plugin list --json` reports hallouminate@hallouminate installed"
    )


CURSOR_HALLOUMINATE_ENTRY = {"command": "hallouminate", "args": ["serve"]}


def cursor_mcp_step() -> PlanStep:
    return hallouminate_steps(FakeRunner(npm_script()))["hallouminate:mcp:cursor"]


def write_cursor_config(home: Path, document: object) -> None:
    (home / ".cursor").mkdir(exist_ok=True)
    (home / ".cursor/mcp.json").write_text(json.dumps(document))


def test_hallouminate_cursor_mcp_postcondition_reads_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = cursor_mcp_step()

    write_cursor_config(tmp_path, {"mcpServers": {"hallouminate": CURSOR_HALLOUMINATE_ENTRY}})
    runner = FakeRunner()
    assert adapter.check_postcondition(step, runner) is True
    assert runner.argvs() == []


def test_hallouminate_cursor_mcp_postcondition_false_when_entry_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = cursor_mcp_step()

    assert adapter.check_postcondition(step, FakeRunner()) is False

    write_cursor_config(tmp_path, {"mcpServers": {"tilth": CURSOR_HALLOUMINATE_ENTRY}})
    assert adapter.check_postcondition(step, FakeRunner()) is False

    (tmp_path / ".cursor/mcp.json").write_text("{not json")
    assert adapter.check_postcondition(step, FakeRunner()) is False


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param({"command": "npx", "args": ["serve"]}, id="wrong-command"),
        pytest.param({"command": "hallouminate", "args": ["mcp"]}, id="wrong-args"),
        pytest.param({"command": "hallouminate"}, id="missing-args"),
        pytest.param({"command": "hallouminate", "args": "serve"}, id="args-not-a-list"),
    ],
)
def test_hallouminate_cursor_mcp_postcondition_false_when_entry_is_wrong(
    entry: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    write_cursor_config(tmp_path, {"mcpServers": {"hallouminate": entry}})

    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    assert adapter.check_postcondition(cursor_mcp_step(), FakeRunner()) is False


def test_hallouminate_config_postcondition_uses_config_validate() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:config-init"]

    validate = ("hallouminate", "config", "validate")
    assert adapter.check_postcondition(step, FakeRunner({validate: outcome(validate)})) is True
    assert (
        adapter.check_postcondition(step, FakeRunner({validate: outcome(validate, exit_code=1)}))
        is False
    )


def validate_output(entries: Sequence[tuple[str, str]]) -> str:
    """The real merged `hallouminate config validate` corpus report."""
    lines = [f"Effective corpora ({len(entries)}):"]
    lines += [f"  - {name:<24} → {path}" for name, path in entries]
    lines.append("ok")
    return "\n".join(lines) + "\n"


def test_hallouminate_repo_postconditions_run_in_the_repository() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    repo = Path("/repos/alpha")
    steps = hallouminate_steps(FakeRunner(npm_script()), (repo,))

    validate = ("hallouminate", "config", "validate")
    # `/./` segments and `~` abbreviation both occur in the real output.
    listing = validate_output(
        [
            ("cheez-wiki", "~/Dev/cheez-wiki/.hallouminate/wiki"),
            ("repo:alpha:wiki", "/repos/alpha/./.hallouminate/wiki"),
        ]
    )
    init_ok = FakeRunner({validate: outcome(validate, stdout=listing)})
    assert (
        adapter.check_postcondition(steps["hallouminate:init-repo:/repos/alpha"], init_ok) is True
    )
    assert init_ok.calls == [(validate, repo)]

    # Validate succeeds, but the repository corpus was never declared.
    init_bad = FakeRunner(
        {validate: outcome(validate, stdout=validate_output([("repo:other:wiki", "/repos/other")]))}
    )
    assert (
        adapter.check_postcondition(steps["hallouminate:init-repo:/repos/alpha"], init_bad) is False
    )

    ground = (
        "hallouminate",
        "ground",
        "repo:alpha:wiki",
        "--corpus",
        "repo:alpha:wiki",
        "--format",
        "json",
        "--limit",
        "1",
    )
    index_ok = FakeRunner({ground: outcome(ground, stdout='{"chunks":[{"path":"a.md"}]}')})
    assert adapter.check_postcondition(steps["hallouminate:index:/repos/alpha"], index_ok) is True
    assert index_ok.calls == [(ground, repo)]

    # The query exits 0 but the corpus is empty: indexing has not converged.
    index_empty = FakeRunner({ground: outcome(ground, stdout='{"chunks":[]}')})
    assert (
        adapter.check_postcondition(steps["hallouminate:index:/repos/alpha"], index_empty) is False
    )


def test_hallouminate_corpus_query_postcondition_parses_json_instead_of_a_raw_substring() -> None:
    # A zero-exit envelope can mention "path" while reporting no results.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    repo = Path("/repos/alpha")
    steps = hallouminate_steps(FakeRunner(npm_script()), (repo,))

    ground = (
        "hallouminate",
        "ground",
        "repo:alpha:wiki",
        "--corpus",
        "repo:alpha:wiki",
        "--format",
        "json",
        "--limit",
        "1",
    )
    degraded = FakeRunner({ground: outcome(ground, stdout='{"chunks": [], "path": null}')})
    assert adapter.check_postcondition(steps["hallouminate:index:/repos/alpha"], degraded) is False


def test_hallouminate_repo_postcondition_reads_an_ascii_rendered_listing() -> None:
    # M-A3: `→` is what the CLI emits today, but a non-UTF-8 locale or a plain
    # renderer prints `->`. Missing it makes every init-repo step FAILED
    # forever, because `config validate` still exits 0.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    repo = Path("/repos/alpha")
    step = hallouminate_steps(FakeRunner(npm_script()), (repo,))[
        "hallouminate:init-repo:/repos/alpha"
    ]

    validate = ("hallouminate", "config", "validate")
    ascii_listing = (
        "Effective corpora (2):\n"
        "  > cheez-wiki       -> ~/Dev/cheez-wiki/.hallouminate/wiki\n"
        "  > repo:alpha:wiki  -> /repos/alpha/./.hallouminate/wiki\n"
        "ok\n"
    )
    runner = FakeRunner({validate: outcome(validate, stdout=ascii_listing)})
    assert adapter.check_postcondition(step, runner) is True


def test_hallouminate_repo_postcondition_rejects_another_repositorys_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # H3: `config validate` reports the merged XDG baseline, so a same-named
    # repository elsewhere on disk already contributes `repo:<name>:wiki`.
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    selected = tmp_path / "work" / "foo"
    steps = hallouminate_steps(FakeRunner(npm_script()), (selected,), (tmp_path / "work",))
    step = steps[f"hallouminate:init-repo:{selected.as_posix()}"]

    validate = ("hallouminate", "config", "validate")
    foreign = ("repo:foo:wiki", "~/Dev/foo/./.hallouminate/wiki")
    baseline = FakeRunner({validate: outcome(validate, stdout=validate_output([foreign]))})
    assert adapter.check_postcondition(step, baseline) is False

    seeded = validate_output([foreign, ("repo:foo:wiki", f"{selected}/./.hallouminate/wiki")])
    ok = FakeRunner({validate: outcome(validate, stdout=seeded)})
    assert adapter.check_postcondition(step, ok) is True


def test_hallouminate_repo_postcondition_resolves_relative_target_against_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # H1: a relative target must resolve against the repository the probe ran
    # in, never the cheese-flow process's own working directory.
    monkeypatch.chdir(tmp_path)
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    repo = Path("/repos/alpha")
    steps = hallouminate_steps(FakeRunner(npm_script()), (repo,))
    step = steps["hallouminate:init-repo:/repos/alpha"]

    validate = ("hallouminate", "config", "validate")
    listing = validate_output([("repo:alpha:wiki", "./.hallouminate/wiki")])
    runner = FakeRunner({validate: outcome(validate, stdout=listing)})
    assert adapter.check_postcondition(step, runner) is True


def test_hallouminate_repo_postcondition_rejects_an_empty_target_from_inside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # H1: `_resolved("")` used to build `PosixPath('.')`, resolving to the
    # cheese-flow process's own CWD rather than the repository. When cheese
    # install runs from inside the selected repository, that false resolution
    # falsely satisfied `is_relative_to`.
    repo = tmp_path / "work" / "alpha"
    repo.mkdir(parents=True)
    monkeypatch.chdir(repo)
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    steps = hallouminate_steps(FakeRunner(npm_script()), (repo,), (tmp_path / "work",))
    step = steps[f"hallouminate:init-repo:{repo.as_posix()}"]

    validate = ("hallouminate", "config", "validate")
    listing = validate_output([("repo:alpha:wiki", "")])
    runner = FakeRunner({validate: outcome(validate, stdout=listing)})
    assert adapter.check_postcondition(step, runner) is False


# --------------------------------------------------------------------------
# easy-cheese
# --------------------------------------------------------------------------


SKILLS_ADD_ARGV = (
    "npx",
    "-y",
    "skills@latest",
    "add",
    "paulnsorensen/easy-cheese",
    "--skill",
    "*",
    "--agent",
    "cursor",
    "--global",
    "--yes",
)


def test_easy_cheese_plans_one_skills_add_per_harness() -> None:
    runner = FakeRunner()
    steps = EasyCheeseAdapter(runner).plan_steps(state())

    assert [s.step_id for s in steps] == [
        "easy-cheese:install:claude-code",
        "easy-cheese:install:codex",
        "easy-cheese:install:cursor",
    ]
    assert steps[2].argv == SKILLS_ADD_ARGV
    assert steps[2].phase is Phase.REGISTER
    assert steps[2].depends_on == ()
    assert runner.argvs() == []


def test_easy_cheese_uses_the_agent_token_the_skills_cli_accepts() -> None:
    steps = steps_by_id(EasyCheeseAdapter(FakeRunner()).plan_steps(state()))

    assert [_agent_token(step) for step in steps.values()] == ["claude-code", "codex", "cursor"]
    assert set(AGENT_TOKENS) == set(ALL_HARNESSES)


def _agent_token(step: PlanStep) -> str:
    return step.argv[step.argv.index("--agent") + 1]


def test_easy_cheese_needs_no_gh_anywhere_in_the_adapter() -> None:
    """acceptance:21 — `gh` is an undeclared prerequisite a cloud box does not have."""
    source = Path(easy_cheese.__file__).read_text(encoding="utf-8")

    assert re.search(r"\bgh\b", source) is None


def test_easy_cheese_skips_a_harness_the_skills_cli_cannot_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harness with no accepted `--agent` token gets no step, not one that cannot converge."""
    monkeypatch.delitem(AGENT_TOKENS, "cursor")

    steps = EasyCheeseAdapter(FakeRunner()).plan_steps(state())

    assert [s.step_id for s in steps] == [
        "easy-cheese:install:claude-code",
        "easy-cheese:install:codex",
    ]


@pytest.fixture
def sandbox_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def easy_cheese_step(harness: str = "claude-code") -> PlanStep:
    return steps_by_id(EasyCheeseAdapter(FakeRunner()).plan_steps(state()))[
        f"easy-cheese:install:{harness}"
    ]


def install_skills(directory: Path, names: Sequence[str]) -> Path:
    """What `skills add --global` leaves on disk: one directory per skill."""
    for name in names:
        (directory / name).mkdir(parents=True, exist_ok=True)
        (directory / name / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("harness", "relative"),
    [
        pytest.param("claude-code", ".claude/skills", id="claude-code"),
        pytest.param("codex", ".agents/skills", id="codex"),
        pytest.param("cursor", ".agents/skills", id="cursor"),
    ],
)
def test_easy_cheese_postcondition_reads_the_harness_skills_directory(
    harness: str, relative: str, sandbox_home: Path
) -> None:
    """Each harness is verified where the `skills` CLI actually writes its pack.

    Codex and Cursor read the shared `.agents/skills` store the CLI treats as
    canonical; Claude Code gets its own directory, linked per skill.
    """
    step = easy_cheese_step(harness)
    adapter = EasyCheeseAdapter(FakeRunner())
    assert adapter.check_postcondition(step, FakeRunner()) is False

    install_skills(sandbox_home / relative, sorted(CORE_SKILLS))

    assert adapter.check_postcondition(step, FakeRunner()) is True
    assert str(sandbox_home / relative) in step.postcondition


def test_easy_cheese_raises_rather_than_guessing_a_directory_for_an_unlisted_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harness with no recorded directory must not fall through to another one's.

    Defaulting would verify a directory the install never wrote and report a
    harness as converged that the pack never reached.
    """
    monkeypatch.delitem(easy_cheese._SKILLS_DIRS, "cursor")

    with pytest.raises(KeyError):
        skills_directory("cursor")


def test_easy_cheese_postcondition_does_not_read_another_harnesss_directory(
    sandbox_home: Path,
) -> None:
    """One harness's pack must never satisfy a harness that reads elsewhere.

    Claude Code's directory and the canonical store are distinct places, and
    collapsing them — in either direction — would report an install that never
    reached the harness the step names.
    """
    adapter = EasyCheeseAdapter(FakeRunner())
    install_skills(sandbox_home / ".claude" / "skills", sorted(CORE_SKILLS))

    assert adapter.check_postcondition(easy_cheese_step("claude-code"), FakeRunner()) is True
    assert adapter.check_postcondition(easy_cheese_step("codex"), FakeRunner()) is False
    assert adapter.check_postcondition(easy_cheese_step("cursor"), FakeRunner()) is False


def test_easy_cheese_postcondition_runs_no_command_so_a_host_without_gh_converges(
    sandbox_home: Path,
) -> None:
    """acceptance:24 — the check is a filesystem read; an unreachable `gh` cannot break it."""
    install_skills(sandbox_home / ".claude" / "skills", sorted(CORE_SKILLS))
    runner = FakeRunner()

    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is True
    assert runner.argvs() == []


def test_easy_cheese_postcondition_requires_the_full_core_quorum(sandbox_home: Path) -> None:
    # The step installs the whole pack; a partial install is not convergence.
    install_skills(sandbox_home / ".claude" / "skills", sorted(CORE_SKILLS)[:-1])

    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), FakeRunner())
        is False
    )


def test_easy_cheese_postcondition_rejects_a_skill_directory_without_its_skill_file(
    sandbox_home: Path,
) -> None:
    """An empty directory of the right name is not an installed skill."""
    skills = install_skills(sandbox_home / ".claude" / "skills", sorted(CORE_SKILLS))
    (skills / "cook" / "SKILL.md").unlink()

    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), FakeRunner())
        is False
    )


def test_easy_cheese_postcondition_ignores_skills_outside_the_core_quorum(
    sandbox_home: Path,
) -> None:
    install_skills(sandbox_home / ".claude" / "skills", [*sorted(CORE_SKILLS), "chezmoi", "prek"])

    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), FakeRunner())
        is True
    )


def test_easy_cheese_postcondition_resolves_a_symlinked_skill(sandbox_home: Path) -> None:
    """The CLI symlinks into the harness directory by default; the check follows links."""
    canonical = install_skills(sandbox_home / ".agents" / "skills", sorted(CORE_SKILLS))
    linked = sandbox_home / ".claude" / "skills"
    linked.mkdir(parents=True)
    for name in sorted(CORE_SKILLS):
        (linked / name).symlink_to(canonical / name, target_is_directory=True)

    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), FakeRunner())
        is True
    )


def test_easy_cheese_postcondition_honours_the_claude_config_dir_override(
    sandbox_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `skills` CLI writes where `CLAUDE_CONFIG_DIR` points, so the check reads there."""
    elsewhere = tmp_path / "claude-config"
    install_skills(elsewhere / "skills", sorted(CORE_SKILLS))
    install_skills(sandbox_home / ".claude" / "skills", ["cook"])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(elsewhere))

    assert skills_directory("claude-code") == elsewhere / "skills"
    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), FakeRunner())
        is True
    )


def test_easy_cheese_postcondition_rejects_a_step_without_a_harness() -> None:
    orphan = PlanStep(
        step_id="easy-cheese:install:none",
        component="easy-cheese",
        phase=Phase.REGISTER,
        argv=("npx", "-y", "skills@latest"),
        postcondition="never",
    )

    with pytest.raises(ValueError, match="has no harness"):
        EasyCheeseAdapter(FakeRunner()).check_postcondition(orphan, FakeRunner())


# --------------------------------------------------------------------------
# Tilth
# --------------------------------------------------------------------------


DARWIN_ARM64_TRIPLE = "aarch64-apple-darwin"
DARWIN_X86_64_TRIPLE = "x86_64-apple-darwin"
LINUX_AARCH64_TRIPLE = "aarch64-unknown-linux-musl"
LINUX_X86_64_TRIPLE = "x86_64-unknown-linux-musl"


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", DARWIN_ARM64_TRIPLE),
        ("Darwin", "x86_64", DARWIN_X86_64_TRIPLE),
        ("Linux", "aarch64", LINUX_AARCH64_TRIPLE),
        ("Linux", "x86_64", LINUX_X86_64_TRIPLE),
    ],
)
def test_target_triple_resolves_supported_platforms(
    system: str, machine: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert _target_triple() == expected


def test_target_triple_rejects_an_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    with pytest.raises(RuntimeError, match="could not resolve"):
        _target_triple()


def test_tilth_plans_registration_and_native_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    runner = FakeRunner()
    steps = TilthAdapter(runner).plan_steps(state())

    assert [s.step_id for s in steps] == [
        "tilth:install",
        "tilth:register:claude-code",
        "tilth:register:codex",
        "tilth:register:cursor",
        "tilth:permission:claude-code",
        "tilth:permission:codex",
        "tilth:permission:cursor",
    ]
    install = steps[0]
    assert install.phase is Phase.INSTALL
    assert install.argv[:2] == ("sh", "-c")
    assert install.depends_on == ()

    binary = str(_bin_dir() / "tilth")
    for register in steps[1:4]:
        assert register.phase is Phase.REGISTER
        assert register.depends_on == ("tilth:install",)
    assert steps[1].argv == (binary, "install", "claude-code", "--edit")
    assert steps[3].argv == (binary, "install", "cursor", "--edit")

    expected = {
        "claude-code": ConfigEdit(
            target=tmp_path / "claude/settings.json",
            pointer="permissions.allow",
            value="mcp__tilth__*",
            mode="append_unique",
        ),
        "codex": ConfigEdit(
            target=tmp_path / "codex/config.toml",
            pointer="mcp_servers.tilth.default_tools_approval_mode",
            value="approve",
            mode="toml_set",
        ),
        "cursor": ConfigEdit(
            target=tmp_path / ".cursor/cli-config.json",
            pointer="permissions.allow",
            value="Mcp(tilth:*)",
            mode="append_unique",
        ),
    }
    planned = steps_by_id(steps)
    for harness, edit in expected.items():
        permission = planned[f"tilth:permission:{harness}"]
        assert permission.depends_on == (f"tilth:register:{harness}",)
        assert permission.config_edit == edit
        assert "configures" in permission.postcondition


def test_tilth_plans_nothing_when_component_not_selected() -> None:
    runner = FakeRunner()
    assert TilthAdapter(runner).plan_steps(state(components=("hallouminate", "easy-cheese"))) == ()
    assert runner.argvs() == []


def test_tilth_install_script_downloads_both_release_assets_with_bounded_curl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    script = TilthAdapter(FakeRunner()).plan_steps(state())[0].argv[2]

    tarball_url = f"{RELEASE_URL}/tilth-{LINUX_X86_64_TRIPLE}.tar.gz"
    assert tarball_url in script
    assert f"{tarball_url}.sha256" in script
    assert "--proto '=https' --tlsv1.2" in script
    assert "--connect-timeout 10 --max-time 60" in script
    assert "--retry 4 --retry-delay 15 --retry-all-errors --retry-max-time 120" in script


def test_tilth_install_script_installs_atomically_into_the_bin_dir() -> None:
    script = TilthAdapter(FakeRunner()).plan_steps(state())[0].argv[2]

    bin_dir = _bin_dir()
    quoted = shlex.quote(str(bin_dir))
    assert f"mkdir -p {quoted}" in script
    assert f"mktemp {quoted}/tilth.XXXXXX" in script
    assert 'mv "$workdir/tilth" "$staged"' in script
    assert 'chmod +x "$staged"' in script
    assert f'mv "$staged" {quoted}/tilth' in script


@pytest.mark.parametrize(
    "bin_dir",
    [
        Path("/opt/bin"),
        Path("/opt/bin with space"),
        Path("/opt/bin's"),
    ],
)
def test_tilth_install_script_is_valid_sh_for_unusual_bin_dirs(bin_dir: Path) -> None:
    script = _install_script(DARWIN_ARM64_TRIPLE, bin_dir)
    result = subprocess.run(["sh", "-n"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


CURL_FIXTURE_SHIM = """#!/bin/sh
if [ "${CURL_FAIL:-}" = "1" ]; then
    exit 22
fi
dest=""
url=""
prev=""
for arg in "$@"; do
    if [ "$prev" = "-o" ]; then
        dest="$arg"
    fi
    case "$arg" in
        http*) url="$arg" ;;
    esac
    prev="$arg"
done
case "$url" in
    *.sha256) cp "$SHA256_FIXTURE" "$dest" ;;
    *) cp "$TARBALL_FIXTURE" "$dest" ;;
esac
"""


def _write_curl_shim(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "curl"
    shim.write_text(CURL_FIXTURE_SHIM, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)


def _build_tarball_fixture(tmp_path: Path) -> Path:
    """A real gzip tarball, built by the system ``tar``, holding one executable
    ``tilth`` script that prints a version line and exits 0."""
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    tilth_script = payload_dir / "tilth"
    tilth_script.write_text("#!/bin/sh\necho 'tilth 0.0.0-test'\n", encoding="utf-8")
    tilth_script.chmod(0o755)
    tarball = tmp_path / "tilth.tar.gz"
    subprocess.run(
        ["tar", "czf", str(tarball), "-C", str(payload_dir), "tilth"],
        check=True,
    )
    return tarball


def test_tilth_install_script_downloads_verifies_and_installs_the_binary(
    tmp_path: Path,
) -> None:
    shim_dir = tmp_path / "shims"
    _write_curl_shim(shim_dir)
    tarball = _build_tarball_fixture(tmp_path)
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    sidecar = tmp_path / "tilth.tar.gz.sha256"
    sidecar.write_text(f"{digest}  tilth.tar.gz\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    mktemp_root = tmp_path / "mktemp-root"
    mktemp_root.mkdir()

    script = _install_script(DARWIN_ARM64_TRIPLE, bin_dir)
    env = dict(os.environ) | {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        "TMPDIR": str(mktemp_root),
        "TARBALL_FIXTURE": str(tarball),
        "SHA256_FIXTURE": str(sidecar),
    }

    result = subprocess.run(
        ["sh", "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    installed = bin_dir / "tilth"
    assert installed.exists()
    assert os.access(installed, os.X_OK)
    run = subprocess.run([str(installed)], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0
    assert "tilth" in run.stdout
    assert list(mktemp_root.iterdir()) == []


def test_tilth_install_script_refuses_and_installs_nothing_on_digest_mismatch(
    tmp_path: Path,
) -> None:
    shim_dir = tmp_path / "shims"
    _write_curl_shim(shim_dir)
    tarball = _build_tarball_fixture(tmp_path)
    correct_digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    wrong_digest = "0" * 64
    assert wrong_digest != correct_digest
    sidecar = tmp_path / "tilth.tar.gz.sha256"
    sidecar.write_text(f"{wrong_digest}  tilth.tar.gz\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    mktemp_root = tmp_path / "mktemp-root"
    mktemp_root.mkdir()

    script = _install_script(DARWIN_ARM64_TRIPLE, bin_dir)
    env = dict(os.environ) | {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        "TMPDIR": str(mktemp_root),
        "TARBALL_FIXTURE": str(tarball),
        "SHA256_FIXTURE": str(sidecar),
    }

    result = subprocess.run(
        ["sh", "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode != 0
    assert not (bin_dir / "tilth").exists()
    assert "refusing to install tilth — checksum mismatch" in result.stderr
    assert f"  expected {wrong_digest}" in result.stderr
    assert f"  actual   {correct_digest}" in result.stderr
    assert list(mktemp_root.iterdir()) == []


def test_tilth_install_script_reports_context_and_installs_nothing_on_download_failure(
    tmp_path: Path,
) -> None:
    shim_dir = tmp_path / "shims"
    _write_curl_shim(shim_dir)
    tarball = _build_tarball_fixture(tmp_path)
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    sidecar = tmp_path / "tilth.tar.gz.sha256"
    sidecar.write_text(f"{digest}  tilth.tar.gz\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    mktemp_root = tmp_path / "mktemp-root"
    mktemp_root.mkdir()

    script = _install_script(DARWIN_ARM64_TRIPLE, bin_dir)
    env = dict(os.environ) | {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        "TMPDIR": str(mktemp_root),
        "TARBALL_FIXTURE": str(tarball),
        "SHA256_FIXTURE": str(sidecar),
        "CURL_FAIL": "1",
    }

    result = subprocess.run(
        ["sh", "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode != 0
    assert not (bin_dir / "tilth").exists()
    tarball_url = f"{RELEASE_URL}/tilth-{DARWIN_ARM64_TRIPLE}.tar.gz"
    assert (
        f"cheese: could not download tilth for {DARWIN_ARM64_TRIPLE} from {tarball_url}"
        in result.stderr
    )


def test_tilth_bin_dir_honours_xdg_bin_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_BIN_HOME", "/opt/bin")
    assert _bin_dir() == Path("/opt/bin")


def test_tilth_install_postcondition_checks_the_installed_binary_version() -> None:
    binary = str(_bin_dir() / "tilth")
    adapter = TilthAdapter(FakeRunner())
    install_step = steps_by_id(adapter.plan_steps(state()))["tilth:install"]

    ok_runner = FakeRunner({(binary, "--version"): outcome((binary, "--version"))})
    assert adapter.check_postcondition(install_step, ok_runner) is True

    failing_runner = FakeRunner(
        {(binary, "--version"): outcome((binary, "--version"), exit_code=1)}
    )
    assert adapter.check_postcondition(install_step, failing_runner) is False


def tilth_step(harness: str) -> PlanStep:
    return steps_by_id(TilthAdapter(FakeRunner()).plan_steps(state()))[f"tilth:register:{harness}"]


def test_tilth_permission_postcondition_requires_the_canonical_claude_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    adapter = TilthAdapter(FakeRunner())
    permission = steps_by_id(adapter.plan_steps(state()))["tilth:permission:claude-code"]
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"permissions": {"allow": ["mcp__tilth"]}}), encoding="utf-8")

    assert adapter.check_postcondition(permission, FakeRunner()) is False

    settings.write_text(json.dumps({"permissions": {"allow": ["mcp__tilth__*"]}}), encoding="utf-8")
    assert adapter.check_postcondition(permission, FakeRunner()) is True


EDIT_ENTRY = {"command": "npx", "args": ["tilth", "--mcp", "--edit"], "env": {}}
NO_EDIT_ENTRY = {"command": "npx", "args": ["tilth", "--mcp"], "env": {}}
# `tilth install` writes the absolute executable path unless it runs from a
# node_modules shim (install.rs:245-267), which is the global-install case.
GLOBAL_EDIT_ENTRY = {
    "command": "/home/paul/.local/bin/tilth",
    "args": ["--mcp", "--edit"],
    "env": {},
}
GLOBAL_NO_EDIT_ENTRY = {"command": "/home/paul/.local/bin/tilth", "args": ["--mcp"], "env": {}}


def test_launches_tilth_rejects_a_staging_artifact_command() -> None:
    assert _launches_tilth("/home/paul/.local/bin/tilth") is True
    assert _launches_tilth("/home/paul/.local/bin/tilth.XXXXXX") is False


def test_launches_tilth_rejects_a_bare_command() -> None:
    assert _launches_tilth("tilth") is False


def test_tilth_postcondition_accepts_a_globally_installed_absolute_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner())

    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": GLOBAL_EDIT_ENTRY}}))
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is True


def test_tilth_postcondition_false_when_a_global_entry_lacks_edit_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner())

    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"tilth": GLOBAL_NO_EDIT_ENTRY}})
    )
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {"command": "/usr/bin/other-server", "args": ["--mcp", "--edit"]}, id="foreign-binary"
        ),
        pytest.param({"command": "npx", "args": ["other", "--mcp", "--edit"]}, id="npx-other-pkg"),
        pytest.param({"command": "npx", "args": ["--mcp", "--edit"]}, id="npx-without-package"),
    ],
)
def test_tilth_postcondition_rejects_a_foreign_command(
    entry: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": entry}}))

    adapter = TilthAdapter(FakeRunner())
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


def test_tilth_postcondition_reads_claude_code_and_cursor_json_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner())
    runner = FakeRunner()

    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": EDIT_ENTRY}}))
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"tilth": EDIT_ENTRY}}))

    assert adapter.check_postcondition(tilth_step("claude-code"), runner) is False
    assert adapter.check_postcondition(tilth_step("cursor"), runner) is False
    assert runner.argvs() == []


def test_tilth_postcondition_reads_the_codex_toml_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/config.toml").write_text(
        'model = "gpt-5"\n\n[mcp_servers.tilth]\n'
        'command = "npx"\nargs = ["tilth", "--mcp", "--edit"]\n'
    )

    adapter = TilthAdapter(FakeRunner())
    assert adapter.check_postcondition(tilth_step("codex"), FakeRunner()) is False


def test_tilth_postcondition_false_when_edit_mode_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": NO_EDIT_ENTRY}}))

    adapter = TilthAdapter(FakeRunner())
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


def test_tilth_postcondition_false_when_config_absent_or_unrelated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner())

    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False

    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"other": EDIT_ENTRY}}))
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False

    (tmp_path / ".claude.json").write_text("{not json")
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


# --------------------------------------------------------------------------
# PlanStep action contract
# --------------------------------------------------------------------------


SAMPLE_EDIT = ConfigEdit(
    target=Path("/home/me/.cursor/mcp.json"),
    pointer="mcpServers.hallouminate",
    value={"command": "hallouminate", "args": ["serve"]},
)


def test_plan_step_rejects_a_step_with_neither_argv_nor_config_edit() -> None:
    with pytest.raises(ValidationError, match="exactly one of argv or config_edit"):
        PlanStep(
            step_id="hallouminate:noop",
            component="hallouminate",
            phase=Phase.REGISTER,
            postcondition="x",
        )


def test_plan_step_rejects_a_step_with_both_argv_and_config_edit() -> None:
    with pytest.raises(ValidationError, match="exactly one of argv or config_edit"):
        PlanStep(
            step_id="hallouminate:both",
            component="hallouminate",
            phase=Phase.REGISTER,
            argv=("hallouminate", "serve"),
            config_edit=SAMPLE_EDIT,
            postcondition="x",
        )


def test_config_edit_requires_an_absolute_target() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        ConfigEdit(target=Path(".cursor/mcp.json"), pointer="mcpServers.hallouminate", value={})


def test_step_result_reports_a_config_edit_step_with_an_empty_argv() -> None:
    step = PlanStep(
        step_id="hallouminate:mcp:cursor",
        component="hallouminate",
        harness="cursor",
        phase=Phase.REGISTER,
        config_edit=SAMPLE_EDIT,
        postcondition="the cursor MCP entry is present",
    )
    result = StepResult(
        step_id=step.step_id,
        component=step.component,
        harness=step.harness,
        phase=step.phase,
        argv=step.argv,
        postcondition=step.postcondition,
        status=StepStatus.SUCCEEDED,
        elapsed_ms=0,
    )

    assert result.model_dump()["argv"] == ()


# --------------------------------------------------------------------------
# Cross-adapter invariants
# --------------------------------------------------------------------------


def all_planned_steps() -> tuple[PlanStep, ...]:
    runner = FakeRunner(npm_script())
    adapters = default_component_adapters(runner)
    desired = state(selected=(Path("/repos/alpha"),))
    return tuple(step for adapter in adapters.values() for step in adapter.plan_steps(desired))


def test_default_component_adapters_cover_every_component() -> None:
    adapters = default_component_adapters(FakeRunner(npm_script()))
    assert set(adapters) == {"hallouminate", "easy-cheese", "tilth"}
    assert all(name == adapter.name for name, adapter in adapters.items())


# The single step allowed to overwrite, and why: `hallouminate config init`
# refuses an existing config without `--force`, and its postcondition
# (`config validate` succeeds) means the step is skipped unless that config is
# already broken. Every other step must reach its postcondition without
# destroying user state — a new entry here needs the same guarantee.
FORCING_STEPS = frozenset({"hallouminate:config-init"})


def test_no_planned_argv_passes_force_except_the_declared_step() -> None:
    for step in all_planned_steps():
        if step.step_id in FORCING_STEPS:
            continue
        assert "--force" not in step.argv, step.step_id
        assert "-f" not in step.argv, step.step_id


def test_every_forcing_step_is_guarded_by_a_postcondition_that_skips_it() -> None:
    """`--force` is only safe where a satisfied postcondition prevents the mutation."""
    for step in all_planned_steps():
        if step.step_id in FORCING_STEPS:
            assert step.postcondition, step.step_id


def test_planned_step_ids_are_unique_and_dependencies_resolve_in_order() -> None:
    steps = all_planned_steps()
    ids = [step.step_id for step in steps]
    assert len(ids) == len(set(ids))

    seen: set[str] = set()
    for step in steps:
        assert set(step.depends_on) <= seen, step.step_id
        seen.add(step.step_id)


def test_planning_is_deterministic() -> None:
    assert [s.model_dump() for s in all_planned_steps()] == [
        s.model_dump() for s in all_planned_steps()
    ]
