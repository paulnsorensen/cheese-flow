"""Doctor tests: postconditions only, no mutation of cheese-managed state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.adapters import default_component_adapters
from cheese_flow.adapters.easy_cheese import CORE_SKILLS
from cheese_flow.doctor import verify_desired_state
from cheese_flow.models import (
    CommandOutcome,
    ConfigEdit,
    ConfigEditSummary,
    DesiredState,
    Phase,
    PlanStep,
    ReportStatus,
    StepStatus,
)
from test_install import FakeRunner, ScriptedAdapter, step

STATE = DesiredState(harnesses=("claude-code",), components=("hallouminate", "easy-cheese"))

HALLOUMINATE_VERSION = "0.42.1"


def statuses(report: object) -> list[tuple[str, StepStatus]]:
    return [(result.step_id, result.status) for result in report.results]  # type: ignore[attr-defined]


def test_all_postconditions_satisfied_reports_success() -> None:
    steps = (step("a"), step("b", depends_on=("a",)))
    adapter = ScriptedAdapter("hallouminate", steps, {"a": [True], "b": [True]})
    easy = ScriptedAdapter("easy-cheese", ())
    runner = FakeRunner()

    report = verify_desired_state(STATE, {"hallouminate": adapter, "easy-cheese": easy}, runner)

    assert report.status is ReportStatus.SUCCEEDED
    assert statuses(report) == [("a", StepStatus.SUCCEEDED), ("b", StepStatus.SUCCEEDED)]
    assert report.manifest == STATE
    assert [s.step_id for s in report.plan.steps] == ["a", "b"]
    assert report.results[0].exit_code is None
    assert report.results[0].stdout_tail is None
    assert report.results[0].remediation is None


def test_doctor_checks_every_step_even_after_a_failure() -> None:
    steps = (step("a"), step("b", depends_on=("a",)), step("c"))
    adapter = ScriptedAdapter("hallouminate", steps, {"a": [False], "b": [True], "c": [False]})
    easy = ScriptedAdapter("easy-cheese", ())

    report = verify_desired_state(
        STATE, {"hallouminate": adapter, "easy-cheese": easy}, FakeRunner()
    )

    assert statuses(report) == [
        ("a", StepStatus.FAILED),
        ("b", StepStatus.SUCCEEDED),
        ("c", StepStatus.FAILED),
    ]
    assert report.status is ReportStatus.FAILED
    assert adapter.checked == ["a", "b", "c"]
    assert report.results[0].remediation == "postcondition not satisfied: a holds"


def test_doctor_redacts_secrets_in_reported_argv(tmp_path: Path) -> None:
    argv = ("gh", "auth", "status", "--token", "ghp_secret")
    config_secret = ConfigEdit(
        target=tmp_path / "mcp.json",
        pointer="mcpServers.x.token",
        value={"token": "ghp_config_secret"},
    )
    steps = (step("a", argv=argv), step("b", config_edit=config_secret))
    adapter = ScriptedAdapter("hallouminate", steps, {"a": [True], "b": [False]})
    easy = ScriptedAdapter("easy-cheese", ())

    report = verify_desired_state(
        STATE, {"hallouminate": adapter, "easy-cheese": easy}, FakeRunner()
    )

    assert report.results[0].argv == ("gh", "auth", "status", "--token", "***")

    serialized = json.dumps(report.model_dump(mode="json"))
    assert "ghp_secret" not in serialized
    assert "ghp_config_secret" not in serialized


def test_doctor_never_applies_a_config_edit(tmp_path: Path) -> None:
    from cheese_flow.models import ConfigEdit

    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    before = target.read_bytes()
    edited = PlanStep(
        step_id="cursor",
        component="hallouminate",
        phase=Phase.REGISTER,
        config_edit=ConfigEdit(target=target, pointer="mcpServers.x", value={"command": "x"}),
        postcondition="cursor holds x",
    )
    adapter = ScriptedAdapter("hallouminate", (edited,), {"cursor": [False]})
    easy = ScriptedAdapter("easy-cheese", ())

    report = verify_desired_state(
        STATE, {"hallouminate": adapter, "easy-cheese": easy}, FakeRunner()
    )

    assert statuses(report) == [("cursor", StepStatus.FAILED)]
    assert target.read_bytes() == before


def _readonly_script(version: str) -> dict[tuple[str, ...], CommandOutcome]:
    def ok(argv: tuple[str, ...], stdout: str) -> CommandOutcome:
        return CommandOutcome(argv=argv, exit_code=0, stdout=stdout, stderr="", elapsed_ms=1)

    # `gh skill list` reports the whole pack; the postcondition needs the full
    # core quorum, and each entry carries the sourceURL gh derives from the
    # installed SKILL.md frontmatter.
    skills = json.dumps(
        [
            {
                "agentHosts": ["claude-code", "cursor"],
                "scope": "user",
                "skillName": name,
                "sourceURL": "https://github.com/paulnsorensen/easy-cheese",
            }
            for name in sorted(CORE_SKILLS)
        ]
    )
    marketplaces = json.dumps(
        [{"name": "hallouminate", "source": "github", "repo": "paulnsorensen/hallouminate"}]
    )
    fields = "agentHosts,scope,skillName,sourceURL"
    return {
        ("npm", "view", "hallouminate@latest", "version"): ok(
            ("npm", "view", "hallouminate@latest", "version"), version
        ),
        ("hallouminate", "--version"): ok(("hallouminate", "--version"), f"hallouminate {version}"),
        ("claude", "plugin", "marketplace", "list", "--json"): ok(
            ("claude", "plugin", "marketplace", "list", "--json"), marketplaces
        ),
        ("claude", "plugin", "list", "--json"): ok(
            ("claude", "plugin", "list", "--json"),
            json.dumps([{"id": "hallouminate@hallouminate", "scope": "user", "enabled": True}]),
        ),
        ("hallouminate", "config", "validate"): ok(("hallouminate", "config", "validate"), "ok"),
        ("gh", "skill", "list", "--agent", "claude-code", "--scope", "user", "--json", fields): ok(
            ("gh", "skill", "list", "--agent", "claude-code", "--scope", "user", "--json", fields),
            skills,
        ),
        ("gh", "skill", "list", "--agent", "cursor", "--scope", "user", "--json", fields): ok(
            ("gh", "skill", "list", "--agent", "cursor", "--scope", "user", "--json", fields),
            skills,
        ),
    }


def test_doctor_with_real_adapters_runs_only_read_only_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cursor_config = tmp_path / ".cursor" / "mcp.json"
    cursor_config.parent.mkdir()
    cursor_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hallouminate": {"command": "hallouminate", "args": ["serve"]},
                    "other": {"command": "other"},
                }
            }
        ),
        encoding="utf-8",
    )
    before = cursor_config.read_bytes()
    state = DesiredState(
        harnesses=("claude-code", "cursor"), components=("hallouminate", "easy-cheese")
    )
    runner = FakeRunner(_readonly_script(HALLOUMINATE_VERSION))

    report = verify_desired_state(state, default_component_adapters(runner), runner)

    assert report.status is ReportStatus.SUCCEEDED
    assert runner.argvs() == [
        ("npm", "view", "hallouminate@latest", "version"),
        ("hallouminate", "--version"),
        ("claude", "plugin", "marketplace", "list", "--json"),
        ("claude", "plugin", "list", "--json"),
        ("hallouminate", "config", "validate"),
        (
            "gh",
            "skill",
            "list",
            "--agent",
            "claude-code",
            "--scope",
            "user",
            "--json",
            "agentHosts,scope,skillName,sourceURL",
        ),
        (
            "gh",
            "skill",
            "list",
            "--agent",
            "cursor",
            "--scope",
            "user",
            "--json",
            "agentHosts,scope,skillName,sourceURL",
        ),
    ]
    assert cursor_config.read_bytes() == before
    assert [result.step_id for result in report.results] == [
        "hallouminate:npm-install",
        "hallouminate:marketplace:claude-code",
        "hallouminate:plugin:claude-code",
        "hallouminate:mcp:cursor",
        "hallouminate:config-init",
        "easy-cheese:install:claude-code",
        "easy-cheese:install:cursor",
    ]


def test_doctor_identifies_the_file_a_config_edit_step_targets(tmp_path: Path) -> None:
    """A config-edit step reports empty argv, so doctor must name its target too.

    Apply already carried the summary; doctor did not, so ``cheese doctor --json``
    showed ``argv: []`` with ``config_edit: null`` and no way to tell which file
    the step is about.
    """
    target = tmp_path / "mcp.json"
    edited = step(
        "hallouminate:mcp:cursor",
        config_edit=ConfigEdit(target=target, pointer="mcpServers.hallouminate", value={"a": 1}),
        phase=Phase.REGISTER,
    )
    adapters = {
        "hallouminate": ScriptedAdapter("hallouminate", (edited,), {edited.step_id: [True]}),
        "easy-cheese": ScriptedAdapter("easy-cheese", ()),
    }

    report = verify_desired_state(STATE, adapters, FakeRunner())

    result = report.results[0]
    assert result.argv == ()
    assert result.config_edit == ConfigEditSummary(target=target, pointer="mcpServers.hallouminate")
