"""Planning and apply tests driven through scripted adapters and a fake ``CommandRunner``."""

from __future__ import annotations

import json
import signal
from collections.abc import Sequence
from pathlib import Path

import pytest
from cheese_flow.install import (
    TAIL_LIMIT,
    apply_install_plan,
    build_install_plan,
)
from cheese_flow.models import (
    CommandOutcome,
    ComponentName,
    ConfigEdit,
    DesiredState,
    InstallPlan,
    Phase,
    PlanStep,
    ReportStatus,
    RepositorySelection,
    StepStatus,
)

STATE = DesiredState(harnesses=("claude-code",), components=("hallouminate", "easy-cheese"))


class FakeRunner:
    """Records argv and replays scripted outcomes keyed by exact argv."""

    def __init__(
        self,
        script: dict[tuple[str, ...], CommandOutcome] | None = None,
        *,
        raise_signal_on: tuple[str, ...] | None = None,
    ) -> None:
        self.script = dict(script or {})
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []
        self.forwarded: list[int] = []
        self._raise_signal_on = raise_signal_on

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        key = tuple(argv)
        self.calls.append((key, cwd))
        if self._raise_signal_on is not None and key == self._raise_signal_on:
            signal.raise_signal(signal.SIGINT)
        if key in self.script:
            return self.script[key]
        return CommandOutcome(argv=key, exit_code=0, stdout="", stderr="", elapsed_ms=1)

    def forward_signal(self, signum: int) -> None:
        self.forwarded.append(signum)

    def argvs(self) -> list[tuple[str, ...]]:
        return [argv for argv, _ in self.calls]


class ScriptedAdapter:
    """Adapter whose steps and postcondition answers are fixed up front."""

    def __init__(
        self,
        name: ComponentName,
        steps: tuple[PlanStep, ...],
        checks: dict[str, list[bool]] | None = None,
    ) -> None:
        self.name = name
        self._steps = steps
        self._checks = {key: list(values) for key, values in (checks or {}).items()}
        self.checked: list[str] = []

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        return self._steps if self.name in state.components else ()

    def check_postcondition(self, step: PlanStep, runner: object) -> bool:
        self.checked.append(step.step_id)
        answers = self._checks.setdefault(step.step_id, [False, True])
        return answers.pop(0) if len(answers) > 1 else answers[0]


def step(
    step_id: str,
    *,
    component: ComponentName = "hallouminate",
    argv: tuple[str, ...] | None = None,
    config_edit: ConfigEdit | None = None,
    depends_on: tuple[str, ...] = (),
    repository: Path | None = None,
    phase: Phase = Phase.INSTALL,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        component=component,
        phase=phase,
        argv=() if config_edit is not None else (argv or ("run", step_id)),
        config_edit=config_edit,
        postcondition=f"{step_id} holds",
        depends_on=depends_on,
        repository=repository,
    )


def plan_of(*steps: PlanStep, state: DesiredState = STATE) -> InstallPlan:
    return InstallPlan(manifest=state, steps=steps)


def statuses(report: object) -> list[tuple[str, StepStatus]]:
    return [(result.step_id, result.status) for result in report.results]  # type: ignore[attr-defined]


def test_plan_orders_components_canonically_and_skips_unselected() -> None:
    state = DesiredState(harnesses=("codex",), components=("easy-cheese", "hallouminate"))
    adapters = {
        "hallouminate": ScriptedAdapter("hallouminate", (step("h1"),)),
        "easy-cheese": ScriptedAdapter("easy-cheese", (step("e1", component="easy-cheese"),)),
        "tilth": ScriptedAdapter("tilth", (step("t1", component="tilth"),)),
    }

    plan = build_install_plan(state, adapters)

    assert [s.step_id for s in plan.steps] == ["h1", "e1"]
    assert plan.manifest == state


def test_plan_rejects_a_selected_component_without_an_adapter() -> None:
    adapters = {"hallouminate": ScriptedAdapter("hallouminate", (step("h1"),))}

    with pytest.raises(ValueError, match="easy-cheese"):
        build_install_plan(STATE, adapters)


def test_satisfied_postcondition_skips_the_mutation_entirely() -> None:
    adapter = ScriptedAdapter("hallouminate", (step("h1"),), {"h1": [True]})
    runner = FakeRunner()

    report = apply_install_plan(plan_of(step("h1")), runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [("h1", StepStatus.SKIPPED)]
    assert report.status is ReportStatus.SUCCEEDED
    assert runner.argvs() == []
    assert adapter.checked == ["h1"]
    assert report.results[0].argv == ("run", "h1")
    assert report.results[0].exit_code is None


def test_failure_blocks_transitive_dependents_and_leaves_unrelated_work_running() -> None:
    steps = (
        step("a"),
        step("b", depends_on=("a",)),
        step("c", depends_on=("b",)),
        step("d"),
    )
    adapter = ScriptedAdapter(
        "hallouminate",
        steps,
        {"a": [False, False], "b": [False, True], "c": [False, True], "d": [False, True]},
    )
    runner = FakeRunner()

    report = apply_install_plan(plan_of(*steps), runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [
        ("a", StepStatus.FAILED),
        ("b", StepStatus.BLOCKED),
        ("c", StepStatus.BLOCKED),
        ("d", StepStatus.SUCCEEDED),
    ]
    assert report.status is ReportStatus.FAILED
    assert runner.argvs() == [("run", "a"), ("run", "d")]
    assert adapter.checked == ["a", "a", "d", "d"]
    assert report.results[1].remediation == "blocked by unmet dependencies: a"


def test_zero_exit_that_does_not_converge_is_a_failure() -> None:
    outcome = CommandOutcome(
        argv=("run", "a"), exit_code=0, stdout="all good", stderr="", elapsed_ms=4
    )
    adapter = ScriptedAdapter("hallouminate", (step("a"),), {"a": [False, False]})
    runner = FakeRunner({("run", "a"): outcome})

    report = apply_install_plan(plan_of(step("a")), runner, adapters={"hallouminate": adapter})

    result = report.results[0]
    assert result.status is StepStatus.FAILED
    assert result.exit_code == 0
    assert result.stdout_tail == "all good"
    assert result.remediation == "postcondition still unsatisfied: a holds"


def test_config_edit_sets_the_pointer_and_preserves_surrounding_config(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "mcp.json"
    target.parent.mkdir()
    target.write_text(
        json.dumps({"keep": {"me": 1}, "mcpServers": {"other": {"command": "other"}}}),
        encoding="utf-8",
    )
    edit = ConfigEdit(
        target=target, pointer="mcpServers.hallouminate", value={"command": "hallouminate"}
    )
    edited = step("cursor", config_edit=edit, phase=Phase.REGISTER)
    adapter = ScriptedAdapter("hallouminate", (edited,), {"cursor": [False, True]})
    runner = FakeRunner()

    report = apply_install_plan(plan_of(edited), runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [("cursor", StepStatus.SUCCEEDED)]
    assert report.results[0].argv == ()
    assert runner.argvs() == []
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "keep": {"me": 1},
        "mcpServers": {"other": {"command": "other"}, "hallouminate": {"command": "hallouminate"}},
    }


def test_config_edit_creates_a_missing_target_without_touching_other_steps(tmp_path: Path) -> None:
    target = tmp_path / "cursor" / "mcp.json"
    edit = ConfigEdit(target=target, pointer="mcpServers.tilth", value={"command": "npx"})
    edited = step("cursor", config_edit=edit, phase=Phase.REGISTER)
    adapter = ScriptedAdapter("hallouminate", (edited,), {"cursor": [False, True]})

    report = apply_install_plan(plan_of(edited), FakeRunner(), adapters={"hallouminate": adapter})

    assert statuses(report) == [("cursor", StepStatus.SUCCEEDED)]
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "mcpServers": {"tilth": {"command": "npx"}}
    }


def test_config_edit_never_clobbers_an_unparseable_target(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_bytes(b"{ this is not json")
    edit = ConfigEdit(target=target, pointer="mcpServers.tilth", value={"command": "npx"})
    edited = step("cursor", config_edit=edit, phase=Phase.REGISTER)
    adapter = ScriptedAdapter("hallouminate", (edited,), {"cursor": [False, False]})

    report = apply_install_plan(plan_of(edited), FakeRunner(), adapters={"hallouminate": adapter})

    assert statuses(report) == [("cursor", StepStatus.FAILED)]
    assert target.read_bytes() == b"{ this is not json"
    assert "mcp.json" in (report.results[0].remediation or "")


def make_repository(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def test_repository_drift_blocks_only_that_repository(tmp_path: Path) -> None:
    drifted = make_repository(tmp_path / "drifted")
    healthy = make_repository(tmp_path / "healthy")
    steps = (
        step("global"),
        step("init-drifted", repository=drifted, phase=Phase.INITIALIZE),
        step("index-drifted", repository=drifted, phase=Phase.INITIALIZE),
        step("init-healthy", repository=healthy, phase=Phase.INITIALIZE),
    )
    adapter = ScriptedAdapter("hallouminate", steps)
    runner = FakeRunner()
    plan = plan_of(*steps)
    (drifted / ".git").rmdir()

    report = apply_install_plan(plan, runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [
        ("global", StepStatus.SUCCEEDED),
        ("init-drifted", StepStatus.BLOCKED),
        ("index-drifted", StepStatus.BLOCKED),
        ("init-healthy", StepStatus.SUCCEEDED),
    ]
    assert report.status is ReportStatus.FAILED
    assert runner.argvs() == [("run", "global"), ("run", "init-healthy")]
    assert str(drifted) in (report.results[1].remediation or "")


def test_selected_worktree_collision_blocks_both_repositories(tmp_path: Path) -> None:
    main = make_repository(tmp_path / "main")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'linked'}\n")
    (main / ".git" / "worktrees" / "linked").mkdir(parents=True)
    (main / ".git" / "worktrees" / "linked" / "commondir").write_text("../..\n")
    steps = (
        step("init-main", repository=main, phase=Phase.INITIALIZE),
        step("init-linked", repository=linked, phase=Phase.INITIALIZE),
    )
    adapter = ScriptedAdapter("hallouminate", steps)

    report = apply_install_plan(plan_of(*steps), FakeRunner(), adapters={"hallouminate": adapter})

    assert statuses(report) == [
        ("init-main", StepStatus.BLOCKED),
        ("init-linked", StepStatus.BLOCKED),
    ]


def test_interrupt_forwards_the_signal_postchecks_and_stops_scheduling() -> None:
    steps = (step("a"), step("b"), step("c"))
    adapter = ScriptedAdapter(
        "hallouminate", steps, {"a": [False, True], "b": [False, False], "c": [False, True]}
    )
    runner = FakeRunner(raise_signal_on=("run", "b"))

    report = apply_install_plan(plan_of(*steps), runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [
        ("a", StepStatus.SUCCEEDED),
        ("b", StepStatus.INTERRUPTED),
        ("c", StepStatus.INTERRUPTED),
    ]
    assert report.status is ReportStatus.INTERRUPTED
    assert runner.forwarded == [signal.SIGINT]
    assert runner.argvs() == [("run", "a"), ("run", "b")]
    assert adapter.checked == ["a", "a", "b", "b"]


def test_interrupt_keeps_a_converged_in_flight_step_successful() -> None:
    steps = (step("a"), step("b"))
    adapter = ScriptedAdapter("hallouminate", steps, {"a": [False, True], "b": [False, True]})
    runner = FakeRunner(raise_signal_on=("run", "a"))

    report = apply_install_plan(plan_of(*steps), runner, adapters={"hallouminate": adapter})

    assert statuses(report) == [
        ("a", StepStatus.SUCCEEDED),
        ("b", StepStatus.INTERRUPTED),
    ]
    assert report.status is ReportStatus.INTERRUPTED


def test_default_sigint_handling_is_restored_after_apply() -> None:
    before = signal.getsignal(signal.SIGINT)
    adapter = ScriptedAdapter("hallouminate", (step("a"),), {"a": [True]})

    apply_install_plan(plan_of(step("a")), FakeRunner(), adapters={"hallouminate": adapter})

    assert signal.getsignal(signal.SIGINT) is before


def test_secrets_are_redacted_in_argv_and_output_tails() -> None:
    argv = ("gh", "auth", "login", "--token", "ghp_secret", "GITHUB_TOKEN=ghp_other")
    secretive = step("a", argv=argv)
    outcome = CommandOutcome(
        argv=argv,
        exit_code=1,
        stdout="used ghp_secret",
        stderr="rejected ghp_other",
        elapsed_ms=2,
    )
    adapter = ScriptedAdapter("hallouminate", (secretive,), {"a": [False, False]})
    runner = FakeRunner({argv: outcome})

    report = apply_install_plan(plan_of(secretive), runner, adapters={"hallouminate": adapter})

    result = report.results[0]
    assert result.argv == ("gh", "auth", "login", "--token", "***", "GITHUB_TOKEN=***")
    assert result.stdout_tail == "used ***"
    assert result.stderr_tail == "rejected ***"
    assert runner.argvs() == [argv]


def test_output_tails_are_bounded() -> None:
    argv = ("run", "a")
    outcome = CommandOutcome(argv=argv, exit_code=0, stdout="x" * 9000, stderr="", elapsed_ms=1)
    adapter = ScriptedAdapter("hallouminate", (step("a"),), {"a": [False, True]})
    runner = FakeRunner({argv: outcome})

    report = apply_install_plan(plan_of(step("a")), runner, adapters={"hallouminate": adapter})

    assert report.results[0].stdout_tail == "x" * TAIL_LIMIT


def test_repository_steps_run_in_the_repository_working_directory(tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "repo")
    only = step("init", repository=repository, phase=Phase.INITIALIZE)
    adapter = ScriptedAdapter("hallouminate", (only,), {"init": [False, True]})
    runner = FakeRunner()
    state = DesiredState(
        harnesses=("claude-code",),
        components=("hallouminate", "easy-cheese"),
        repositories=RepositorySelection(
            search_roots=(tmp_path,), selected=(repository,), max_depth=1
        ),
    )

    apply_install_plan(plan_of(only, state=state), runner, adapters={"hallouminate": adapter})

    assert runner.calls == [(("run", "init"), repository)]
