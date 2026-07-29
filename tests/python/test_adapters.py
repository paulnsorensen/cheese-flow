"""Adapter contract tests: exact argv, once-per-run version resolution, and
positive postconditions driven entirely through a scripted fake ``CommandRunner``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from cheese_flow.adapters import (
    EasyCheeseAdapter,
    HallouminateAdapter,
    TilthAdapter,
    default_component_adapters,
)
from cheese_flow.adapters.easy_cheese import CORE_SKILLS
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
NPM_VIEW_TILTH = ("npm", "view", "tilth@latest", "version")

HALLOUMINATE_VERSION = "0.42.1"
TILTH_VERSION = "1.7.0"


def npm_script() -> dict[tuple[str, ...], CommandOutcome]:
    return {
        NPM_VIEW_HALLOUMINATE: outcome(NPM_VIEW_HALLOUMINATE, stdout=f"{HALLOUMINATE_VERSION}\n"),
        NPM_VIEW_TILTH: outcome(NPM_VIEW_TILTH, stdout=f"{TILTH_VERSION}\n"),
    }


def state(
    *,
    harnesses: tuple[str, ...] = ALL_HARNESSES,
    components: tuple[str, ...] = ("hallouminate", "easy-cheese", "tilth"),
    selected: tuple[Path, ...] = (),
) -> DesiredState:
    return DesiredState(
        harnesses=harnesses,
        components=components,
        repositories=RepositorySelection(search_roots=(Path("/repos"),), selected=selected),
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
    assert [s.step_id for s in steps if s.harness == "cursor"] == ["hallouminate:mcp:cursor"]


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


def test_hallouminate_omits_the_cursor_mcp_step_when_cursor_is_not_selected() -> None:
    runner = FakeRunner(npm_script())
    steps = HallouminateAdapter(runner).plan_steps(state(harnesses=("claude-code", "codex")))

    assert "hallouminate:mcp:cursor" not in steps_by_id(steps)


def test_hallouminate_config_init_never_forces_and_depends_on_install() -> None:
    runner = FakeRunner(npm_script())
    config = steps_by_id(HallouminateAdapter(runner).plan_steps(state()))[
        "hallouminate:config-init"
    ]

    assert config.argv == ("hallouminate", "config", "init")
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
    assert init.argv == ("hallouminate", "init-repo", "alpha", "--path", "/repos/alpha")
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


def hallouminate_steps(runner: FakeRunner, repos: tuple[Path, ...] = ()) -> dict[str, PlanStep]:
    return steps_by_id(HallouminateAdapter(runner).plan_steps(state(selected=repos)))


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


# Verbatim shapes from the real CLIs.
CODEX_MARKETPLACE_LIST = (
    "MARKETPLACE          ROOT\n"
    "hallouminate         /home/paul/.cache/ap/plugins/hallouminate\n"
    "claude-code-plugins  /home/paul/.codex/.tmp/marketplaces/claude-code-plugins\n"
)
CLAUDE_MARKETPLACE_LIST = (
    "  ❯ hallouminate\n    Source: Directory (/home/paul/.cache/ap/plugins/hallouminate)\n"
)
FOREIGN_MARKETPLACE_LIST = (
    "MARKETPLACE          ROOT\n"
    "claude-code-plugins  /home/paul/.cache/ap/plugins/hallouminate/vendored\n"
)


def test_hallouminate_marketplace_postcondition_reads_the_native_listing() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:marketplace:codex"]

    list_argv = ("codex", "plugin", "marketplace", "list")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CODEX_MARKETPLACE_LIST)})
    assert adapter.check_postcondition(step, ok) is True
    assert ok.argvs() == [list_argv]

    empty = FakeRunner({list_argv: outcome(list_argv, stdout="No marketplaces configured\n")})
    assert adapter.check_postcondition(step, empty) is False


def test_hallouminate_marketplace_postcondition_reads_the_claude_bullet_listing() -> None:
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:marketplace:claude-code"]

    list_argv = ("claude", "plugin", "marketplace", "list")
    ok = FakeRunner({list_argv: outcome(list_argv, stdout=CLAUDE_MARKETPLACE_LIST)})
    assert adapter.check_postcondition(step, ok) is True


def test_hallouminate_marketplace_postcondition_ignores_a_hallouminate_root_path() -> None:
    # M3: the marketplace name lives in the first column; `hallouminate` also
    # appears inside other marketplaces' filesystem ROOTs and must not count.
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    step = hallouminate_steps(FakeRunner(npm_script()))["hallouminate:marketplace:codex"]

    list_argv = ("codex", "plugin", "marketplace", "list")
    foreign = FakeRunner({list_argv: outcome(list_argv, stdout=FOREIGN_MARKETPLACE_LIST)})
    assert adapter.check_postcondition(step, foreign) is False


CLAUDE_PLUGIN_LIST_JSON = json.dumps(
    [
        {
            "id": "hallouminate@hallouminate",
            "version": "0.3.2",
            "scope": "user",
            "enabled": True,
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


def test_hallouminate_repo_postcondition_rejects_another_repositorys_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # H3: `config validate` reports the merged XDG baseline, so a same-named
    # repository elsewhere on disk already contributes `repo:<name>:wiki`.
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = HallouminateAdapter(FakeRunner(npm_script()))
    selected = tmp_path / "work" / "foo"
    steps = hallouminate_steps(FakeRunner(npm_script()), (selected,))
    step = steps[f"hallouminate:init-repo:{selected.as_posix()}"]

    validate = ("hallouminate", "config", "validate")
    foreign = ("repo:foo:wiki", "~/Dev/foo/./.hallouminate/wiki")
    baseline = FakeRunner({validate: outcome(validate, stdout=validate_output([foreign]))})
    assert adapter.check_postcondition(step, baseline) is False

    seeded = validate_output([foreign, ("repo:foo:wiki", f"{selected}/./.hallouminate/wiki")])
    ok = FakeRunner({validate: outcome(validate, stdout=seeded)})
    assert adapter.check_postcondition(step, ok) is True


# --------------------------------------------------------------------------
# easy-cheese
# --------------------------------------------------------------------------


def test_easy_cheese_plans_one_gh_skill_install_per_harness() -> None:
    runner = FakeRunner()
    steps = EasyCheeseAdapter(runner).plan_steps(state())

    assert [s.step_id for s in steps] == [
        "easy-cheese:install:claude-code",
        "easy-cheese:install:codex",
        "easy-cheese:install:cursor",
    ]
    assert steps[2].argv == (
        "gh",
        "skill",
        "install",
        "paulnsorensen/easy-cheese",
        "--all",
        "--agent",
        "cursor",
        "--scope",
        "user",
    )
    assert steps[2].phase is Phase.REGISTER
    assert steps[2].depends_on == ()
    assert runner.argvs() == []


LIST_ARGV = (
    "gh",
    "skill",
    "list",
    "--agent",
    "claude-code",
    "--scope",
    "user",
    "--json",
    "agentHosts,scope,skillName,sourceURL",
)


def gh_list(entries: list[dict[str, object]], *, exit_code: int = 0) -> FakeRunner:
    return FakeRunner(
        {LIST_ARGV: outcome(LIST_ARGV, exit_code=exit_code, stdout=json.dumps(entries))}
    )


def easy_cheese_step() -> PlanStep:
    return steps_by_id(EasyCheeseAdapter(FakeRunner()).plan_steps(state()))[
        "easy-cheese:install:claude-code"
    ]


def test_easy_cheese_postcondition_confirms_source_agent_scope_and_skills() -> None:
    adapter = EasyCheeseAdapter(FakeRunner())
    runner = gh_list(
        [
            {
                "agentHosts": ["claude-code"],
                "scope": "user",
                "skillName": "cook",
                "sourceURL": "https://github.com/paulnsorensen/easy-cheese",
            }
        ]
    )
    assert adapter.check_postcondition(easy_cheese_step(), runner) is True
    assert runner.argvs() == [LIST_ARGV]


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {
                "agentHosts": ["claude-code"],
                "scope": "project",
                "skillName": "cook",
                "sourceURL": "https://github.com/paulnsorensen/easy-cheese",
            },
            id="wrong-scope",
        ),
        pytest.param(
            {
                "agentHosts": ["codex"],
                "scope": "user",
                "skillName": "cook",
                "sourceURL": "https://github.com/paulnsorensen/easy-cheese",
            },
            id="wrong-agent",
        ),
        pytest.param(
            {
                "agentHosts": ["claude-code"],
                "scope": "user",
                "skillName": "cook",
                "sourceURL": "https://github.com/someone/other-skills",
            },
            id="wrong-source",
        ),
        pytest.param(
            {
                "agentHosts": ["claude-code"],
                "scope": "user",
                "skillName": "",
                "sourceURL": "https://github.com/paulnsorensen/easy-cheese",
            },
            id="no-skill-installed",
        ),
    ],
)
def test_easy_cheese_postcondition_rejects_wrong_end_state(entry: dict[str, object]) -> None:
    # `gh skill list` exits 0 in every one of these cases: only the parsed
    # end state distinguishes them.
    assert (
        EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), gh_list([entry]))
        is False
    )


def test_easy_cheese_postcondition_false_on_empty_listing_and_bad_json() -> None:
    adapter = EasyCheeseAdapter(FakeRunner())
    assert adapter.check_postcondition(easy_cheese_step(), gh_list([])) is False

    garbage = FakeRunner({LIST_ARGV: outcome(LIST_ARGV, stdout="not json")})
    assert adapter.check_postcondition(easy_cheese_step(), garbage) is False

    failed = gh_list([], exit_code=1)
    assert adapter.check_postcondition(easy_cheese_step(), failed) is False


def blank_source_entry(name: str, *, harness: str = "claude-code") -> dict[str, object]:
    """A real `gh skill list --json` row: every installed skill reports no source."""
    return {"agentHosts": [harness], "scope": "user", "skillName": name, "sourceURL": ""}


def test_easy_cheese_postcondition_accepts_installed_skills_with_no_source_url() -> None:
    # H1: `gh skill list` reports `sourceURL: ""` for every installed skill, so
    # a source-only check reports FAILED forever on a correct fresh install.
    runner = gh_list([blank_source_entry(name) for name in CORE_SKILLS])
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is True


def test_easy_cheese_postcondition_rejects_a_harness_missing_core_skills() -> None:
    # The name fallback must still discriminate: a harness carrying unrelated
    # skills (real codex/cursor state) is not an easy-cheese install.
    runner = gh_list([blank_source_entry(name) for name in ("chezmoi", "prek", "explain")])
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is False

    partial = gh_list([blank_source_entry(name) for name in sorted(CORE_SKILLS)[:-1]])
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), partial) is False


def test_easy_cheese_postcondition_keeps_source_matching_authoritative() -> None:
    # When gh does populate sourceURL, a full core quorum from a foreign pack
    # must not satisfy the step.
    foreign = [
        {
            "agentHosts": ["claude-code"],
            "scope": "user",
            "skillName": name,
            "sourceURL": "https://github.com/someone/other-skills",
        }
        for name in CORE_SKILLS
    ]
    runner = gh_list(foreign)
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is False


def test_easy_cheese_postcondition_ignores_core_skills_owned_by_another_harness() -> None:
    entries = [blank_source_entry(name, harness="codex") for name in CORE_SKILLS]
    runner = gh_list(entries)
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is False


def test_easy_cheese_accepts_bare_owner_repo_source() -> None:
    runner = gh_list(
        [
            {
                "agentHosts": ["claude-code", "cursor"],
                "scope": "user",
                "skillName": "age",
                "sourceURL": "paulnsorensen/easy-cheese.git",
            }
        ]
    )
    assert EasyCheeseAdapter(FakeRunner()).check_postcondition(easy_cheese_step(), runner) is True


# --------------------------------------------------------------------------
# Tilth
# --------------------------------------------------------------------------


def test_tilth_plans_versioned_npx_install_per_harness() -> None:
    runner = FakeRunner(npm_script())
    steps = TilthAdapter(runner).plan_steps(state())

    assert [s.step_id for s in steps] == [
        "tilth:register:claude-code",
        "tilth:register:codex",
        "tilth:register:cursor",
    ]
    assert steps[0].argv == (
        "npx",
        "--yes",
        f"tilth@{TILTH_VERSION}",
        "install",
        "claude-code",
        "--edit",
    )
    assert steps[2].argv == (
        "npx",
        "--yes",
        f"tilth@{TILTH_VERSION}",
        "install",
        "cursor",
        "--edit",
    )
    assert steps[2].phase is Phase.REGISTER


def test_tilth_resolves_npm_view_once_per_run() -> None:
    runner = FakeRunner(npm_script())
    adapter = TilthAdapter(runner)
    adapter.plan_steps(state())
    adapter.plan_steps(state())

    assert runner.argvs().count(NPM_VIEW_TILTH) == 1


def test_tilth_plans_nothing_when_component_not_selected() -> None:
    runner = FakeRunner(npm_script())
    assert TilthAdapter(runner).plan_steps(state(components=("hallouminate", "easy-cheese"))) == ()
    assert runner.argvs() == []


def tilth_step(harness: str) -> PlanStep:
    return steps_by_id(TilthAdapter(FakeRunner(npm_script())).plan_steps(state()))[
        f"tilth:register:{harness}"
    ]


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


def test_tilth_postcondition_accepts_a_globally_installed_absolute_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner(npm_script()))

    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": GLOBAL_EDIT_ENTRY}}))
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is True


def test_tilth_postcondition_false_when_a_global_entry_lacks_edit_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner(npm_script()))

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

    adapter = TilthAdapter(FakeRunner(npm_script()))
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


def test_tilth_postcondition_reads_claude_code_and_cursor_json_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner(npm_script()))
    runner = FakeRunner()

    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": EDIT_ENTRY}}))
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"tilth": EDIT_ENTRY}}))

    assert adapter.check_postcondition(tilth_step("claude-code"), runner) is True
    assert adapter.check_postcondition(tilth_step("cursor"), runner) is True
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

    adapter = TilthAdapter(FakeRunner(npm_script()))
    assert adapter.check_postcondition(tilth_step("codex"), FakeRunner()) is True


def test_tilth_postcondition_false_when_edit_mode_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tilth": NO_EDIT_ENTRY}}))

    adapter = TilthAdapter(FakeRunner(npm_script()))
    assert adapter.check_postcondition(tilth_step("claude-code"), FakeRunner()) is False


def test_tilth_postcondition_false_when_config_absent_or_unrelated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = TilthAdapter(FakeRunner(npm_script()))

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


def test_no_planned_argv_passes_force() -> None:
    for step in all_planned_steps():
        assert "--force" not in step.argv, step.step_id
        assert "-f" not in step.argv, step.step_id


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
