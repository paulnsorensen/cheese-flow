"""Tests for the Typer ``cheese`` CLI surface (``cheese_flow.cli``).

The v1 surface is exactly two commands: ``install`` and ``doctor``. These tests
own routing, headless output discipline, and persistence rules; planning,
apply, and verification belong to ``install.py`` / ``doctor.py`` and are faked
at their seams.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from cheese_flow import cli
from cheese_flow.cli import app
from cheese_flow.desired_state import load_desired_state
from cheese_flow.models import (
    COMPONENT_NAMES,
    ApplyReport,
    CommandOutcome,
    DesiredState,
    DoctorReport,
    InstallPlan,
    Phase,
    PlanStep,
    ReportStatus,
    RepositorySelection,
    StepResult,
    StepStatus,
)
from cheese_flow.runner import DEFAULT_TIMEOUT_SECONDS
from typer.testing import CliRunner

# Help-text assertions below rely on Typer's plain (Click) help formatter, which
# renders option names deterministically regardless of terminal width. The
# session conftest sets ``TYPER_USE_RICH=0`` before typer is imported; with Rich
# enabled, headless CI panels render with no body text and these assertions fail.
runner = CliRunner()

REMOVED_COMMANDS = (
    "compile",
    "lint",
    "milknado",
    "session-start",
    "mcp",
    "solve-blend",
)

MANIFEST_TOML = """\
harnesses = ["claude-code"]
components = ["hallouminate", "easy-cheese"]

[repositories]
search_roots = ["/srv/code"]
max_depth = 2
selected = ["/srv/code/project"]
"""


class RecordingRunner:
    """A ``CommandRunner`` that records every child process it is asked to run."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        self.commands.append(tuple(argv))
        return CommandOutcome(argv=tuple(argv), exit_code=0, stdout="", stderr="", elapsed_ms=0)


def manifest_state() -> DesiredState:
    return DesiredState(
        harnesses=("claude-code",),
        components=("hallouminate", "easy-cheese"),
        repositories=RepositorySelection(
            search_roots=(Path("/srv/code"),),
            max_depth=2,
            selected=(Path("/srv/code/project"),),
        ),
    )


def a_plan(state: DesiredState) -> InstallPlan:
    return InstallPlan(
        manifest=state,
        steps=(
            PlanStep(
                step_id="hallouminate:install",
                component="hallouminate",
                phase=Phase.INSTALL,
                argv=("npm", "install", "--global", "hallouminate@1.2.3"),
                postcondition="hallouminate --version reports 1.2.3",
            ),
        ),
    )


def a_result(status: StepStatus = StepStatus.SUCCEEDED) -> StepResult:
    return StepResult(
        step_id="hallouminate:install",
        component="hallouminate",
        phase=Phase.INSTALL,
        argv=("npm", "install", "--global", "hallouminate@1.2.3"),
        postcondition="hallouminate --version reports 1.2.3",
        status=status,
        exit_code=0 if status is StepStatus.SUCCEEDED else 1,
        elapsed_ms=12,
    )


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``default_config_path()`` at an empty per-test XDG config home."""
    home = tmp_path / "xdg"
    home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home / "cheese" / "config.toml"


@pytest.fixture
def command_runner(monkeypatch: pytest.MonkeyPatch) -> RecordingRunner:
    recorder = RecordingRunner()
    monkeypatch.setattr(cli, "_default_runner", lambda env=None, *, timeout=None: recorder)
    monkeypatch.setattr(cli, "default_component_adapters", lambda _runner: {})
    return recorder


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    """Fake the sibling-owned plan/apply/verify seams and record every call."""
    recorded: dict[str, list[object]] = {
        "plan": [],
        "apply": [],
        "adapters": [],
        "verify": [],
        "wizard": [],
    }

    def build_install_plan(state: DesiredState, _adapters: object) -> InstallPlan:
        recorded["plan"].append(state)
        return a_plan(state)

    def apply_install_plan(plan: InstallPlan, _runner: object, *, adapters: object) -> ApplyReport:
        recorded["apply"].append(plan)
        recorded["adapters"].append(adapters)
        return ApplyReport(
            status=ReportStatus.SUCCEEDED,
            manifest=plan.manifest,
            plan=plan,
            results=(a_result(),),
        )

    def verify_desired_state(
        state: DesiredState, _adapters: object, _runner: object
    ) -> DoctorReport:
        recorded["verify"].append(state)
        plan = a_plan(state)
        return DoctorReport(
            status=ReportStatus.SUCCEEDED,
            manifest=state,
            plan=plan,
            results=(a_result(),),
        )

    def run_wizard(initial: DesiredState | None) -> DesiredState | None:
        recorded["wizard"].append(initial)
        return manifest_state()

    monkeypatch.setattr(cli, "build_install_plan", build_install_plan)
    monkeypatch.setattr(cli, "apply_install_plan", apply_install_plan)
    monkeypatch.setattr(cli, "verify_desired_state", verify_desired_state)
    monkeypatch.setattr(cli, "run_wizard", run_wizard)
    return recorded


def write_manifest(tmp_path: Path, text: str = MANIFEST_TOML) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ─── Command surface ─────────────────────────────────────────────────────────


def test_root_help_lists_exactly_install_and_doctor() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.stdout
    assert "install" in output
    assert "doctor" in output


def test_root_help_omits_the_purged_v0_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in REMOVED_COMMANDS:
        assert command not in result.stdout, f"purged command still exposed: {command!r}"


def test_purged_commands_are_rejected() -> None:
    for command in REMOVED_COMMANDS:
        result = runner.invoke(app, [command])
        assert result.exit_code != 0, f"purged command still runs: {command!r}"


def test_install_help_documents_its_options() -> None:
    result = runner.invoke(app, ["install", "--help"])
    assert result.exit_code == 0
    output = result.stdout
    for option in ("--config", "--dry-run", "--json", "--harness", "--component", "--repo"):
        assert option in output, f"install help omits {option}"
    assert "--write-config" in output


def test_doctor_help_documents_config_option() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.stdout


def test_doctor_help_omits_install_only_options() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" not in result.stdout
    assert "--json" not in result.stdout


# ─── Headless install (acceptance:148, spec:125) ─────────────────────────────


def test_headless_install_emits_one_json_document_with_the_four_root_keys(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert set(document) == {"status", "manifest", "plan", "results"}
    assert document["status"] == "succeeded"
    assert document["manifest"]["harnesses"] == ["claude-code"]
    assert document["manifest"]["components"] == ["hallouminate", "easy-cheese"]
    assert document["plan"]["steps"][0]["step_id"] == "hallouminate:install"
    assert [entry["status"] for entry in document["results"]] == ["succeeded"]


def test_headless_install_never_runs_the_wizard(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    assert calls["wizard"] == []
    assert calls["apply"] == [a_plan(manifest_state())]


def test_headless_install_stdout_carries_nothing_but_the_json_document(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    # Parsing the whole stream is the assertion: any stray human text breaks it.
    document = json.loads(result.stdout)
    assert result.stdout.strip() == json.dumps(document, indent=2)
    assert "hallouminate" in result.stderr, "progress must be reported on stderr"


def test_headless_install_does_not_rewrite_the_default_manifest(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    assert not config_home.exists()
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TOML


def test_json_flag_without_config_runs_headless_from_the_default_manifest(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    config_home.parent.mkdir(parents=True)
    config_home.write_text(MANIFEST_TOML, encoding="utf-8")

    result = runner.invoke(app, ["install", "--json"])

    assert result.exit_code == 0, result.stderr
    assert calls["wizard"] == []
    assert json.loads(result.stdout)["status"] == "succeeded"


# ─── Option-driven headless install ──────────────────────────────────────────


def test_options_build_the_desired_state_without_a_manifest(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    project = tmp_path / "code" / "project"
    project.mkdir(parents=True)

    result = runner.invoke(
        app,
        [
            "install",
            "--harness",
            "claude-code",
            "--component",
            "hallouminate,easy-cheese",
            "--repo",
            str(project),
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert calls["wizard"] == []
    assert calls["plan"] == [
        DesiredState(
            harnesses=("claude-code",),
            components=("hallouminate", "easy-cheese"),
            repositories=RepositorySelection(
                search_roots=(project.parent.resolve(),),
                selected=(project.resolve(),),
            ),
        )
    ]


@pytest.mark.parametrize(
    ("name", "argv"),
    [
        ("comma-separated", ["--harness", "claude-code,codex"]),
        ("space-separated", ["--harness", "claude-code codex"]),
        ("repeated", ["--harness", "claude-code", "--harness", "codex"]),
        ("mixed", ["--harness", "claude-code, codex"]),
    ],
)
def test_list_options_accept_commas_whitespace_and_repetition(
    name: str, argv: list[str], config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", *argv, "--component", "hallouminate easy-cheese"])

    assert result.exit_code == 0, f"{name}: {result.stderr}"
    state = calls["plan"][0]
    assert state.harnesses == ("claude-code", "codex"), name
    assert state.components == ("hallouminate", "easy-cheese"), name


def test_omitted_component_option_selects_every_component(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", "--harness", "claude-code"])

    assert result.exit_code == 0, result.stderr
    assert calls["plan"][0].components == COMPONENT_NAMES


def test_a_relative_repo_option_resolves_against_the_working_directory(
    tmp_path: Path,
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "code" / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project.parent)

    result = runner.invoke(app, ["install", "--harness", "claude-code", "--repo", "project"])

    assert result.exit_code == 0, result.stderr
    assert calls["plan"][0].repositories.selected == (project.resolve(),)


def test_options_are_ephemeral_unless_write_config_is_passed(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", "--harness", "claude-code"])

    assert result.exit_code == 0, result.stderr
    assert not config_home.exists(), "options must not persist a manifest by default"


def test_write_config_persists_the_option_built_manifest(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    project = tmp_path / "code" / "project"
    project.mkdir(parents=True)

    result = runner.invoke(
        app,
        ["install", "--harness", "codex", "--repo", str(project), "--write-config"],
    )

    assert result.exit_code == 0, result.stderr
    assert load_desired_state(config_home) == calls["plan"][0]


def test_write_config_is_written_before_the_plan_is_applied(
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[bool] = []
    faked = cli.apply_install_plan

    def record(plan: InstallPlan, runner_: object, *, adapters: object) -> ApplyReport:
        written.append(config_home.exists())
        return faked(plan, runner_, adapters=adapters)

    monkeypatch.setattr(cli, "apply_install_plan", record)

    result = runner.invoke(app, ["install", "--harness", "codex", "--write-config"])

    assert result.exit_code == 0, result.stderr
    assert written == [True]


def test_options_combined_with_config_are_rejected_before_planning(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest), "--harness", "claude-code"])

    assert result.exit_code == 2
    assert calls["plan"] == []
    assert command_runner.commands == []
    assert "two sources" in result.stderr


def test_write_config_combined_with_dry_run_is_rejected(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(
        app, ["install", "--harness", "claude-code", "--write-config", "--dry-run"]
    )

    assert result.exit_code == 2
    assert calls["plan"] == []
    assert not config_home.exists()


@pytest.mark.parametrize(
    ("name", "argv", "expected"),
    [
        ("unknown harness", ["--harness", "pi"], "unknown harness names: pi"),
        (
            "missing required component",
            ["--harness", "codex", "--component", "tilth"],
            "components must include required components: hallouminate, easy-cheese",
        ),
        (
            "duplicate harness",
            ["--harness", "codex,codex"],
            "harnesses must not contain duplicates: codex",
        ),
    ],
)
def test_invalid_options_exit_nonzero_before_planning_or_running_anything(
    name: str,
    argv: list[str],
    expected: str,
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
) -> None:
    result = runner.invoke(app, ["install", *argv])

    assert result.exit_code == 2, name
    assert expected in result.stderr, name
    assert calls["plan"] == [], name
    assert command_runner.commands == [], name
    assert not config_home.exists(), name


def test_options_with_dry_run_emit_the_plan_and_change_nothing(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", "--harness", "claude-code", "--dry-run"])

    assert result.exit_code == 0, result.stderr
    assert calls["apply"] == []
    assert not config_home.exists()
    assert json.loads(result.stdout)["plan"]["steps"][0]["step_id"] == "hallouminate:install"


# ─── Invalid manifests fail first (acceptance:145) ───────────────────────────


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("missing required component", 'harnesses = ["codex"]\ncomponents = ["hallouminate"]\n'),
        ("unknown harness", 'harnesses = ["pi"]\ncomponents = ["hallouminate", "easy-cheese"]\n'),
        ("unknown key", 'harnesses = ["codex"]\ncomponents = []\nextra = 1\n'),
        ("not toml", "harnesses = [\n"),
        ("no harnesses", 'harnesses = []\ncomponents = ["hallouminate", "easy-cheese"]\n'),
    ],
)
def test_invalid_manifest_exits_nonzero_before_planning_or_running_anything(
    name: str,
    text: str,
    tmp_path: Path,
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
) -> None:
    manifest = write_manifest(tmp_path, text)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code != 0, f"{name}: expected failure"
    assert calls["plan"] == [], f"{name}: planned despite an invalid manifest"
    assert calls["apply"] == [], f"{name}: applied despite an invalid manifest"
    assert command_runner.commands == [], f"{name}: ran a command despite an invalid manifest"
    assert result.stdout == "", f"{name}: stdout must stay empty on manifest failure"
    assert str(manifest) in result.stderr


def test_missing_manifest_exits_nonzero_with_the_path_on_stderr(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    missing = tmp_path / "nope.toml"

    result = runner.invoke(app, ["install", "--config", str(missing)])

    assert result.exit_code != 0
    assert calls["plan"] == []
    assert command_runner.commands == []
    assert result.stdout == ""
    assert str(missing) in result.stderr


def test_json_flag_without_any_manifest_fails_without_prompting(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", "--json"])

    assert result.exit_code != 0
    assert calls["wizard"] == []
    assert calls["plan"] == []
    assert result.stdout == ""


# ─── Dry run (acceptance:147) ────────────────────────────────────────────────


def test_dry_run_emits_the_plan_without_applying_or_persisting(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest), "--dry-run"])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["results"] == []
    assert [step["argv"] for step in document["plan"]["steps"]] == [
        ["npm", "install", "--global", "hallouminate@1.2.3"]
    ]
    assert calls["plan"] == [manifest_state()]
    assert calls["apply"] == [], "dry-run must not apply"
    assert command_runner.commands == [], "dry-run must execute no package code"
    assert not config_home.exists(), "dry-run must not write managed state"


def test_interactive_dry_run_persists_nothing(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install", "--dry-run"])

    assert result.exit_code == 0, result.stderr
    assert calls["wizard"] == [None]
    assert calls["apply"] == []
    assert command_runner.commands == []
    assert not config_home.exists()


# ─── Failure exit codes (acceptance:151) ─────────────────────────────────────


def test_failed_apply_exits_nonzero_and_still_emits_one_json_document(
    tmp_path: Path,
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path)

    def failing_apply(plan: InstallPlan, _runner: object, *, adapters: object) -> ApplyReport:
        return ApplyReport(
            status=ReportStatus.FAILED,
            manifest=plan.manifest,
            plan=plan,
            results=(a_result(StepStatus.FAILED),),
        )

    monkeypatch.setattr(cli, "apply_install_plan", failing_apply)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code != 0
    document = json.loads(result.stdout)
    assert document["status"] == "failed"
    assert [entry["status"] for entry in document["results"]] == ["failed"]


# ─── Interactive install: persistence and cancellation ───────────────────────


def test_interactive_install_writes_the_manifest_atomically_before_apply(
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_on_disk: list[str] = []

    def apply_install_plan(plan: InstallPlan, _runner: object, *, adapters: object) -> ApplyReport:
        seen_on_disk.append(config_home.read_text(encoding="utf-8"))
        return ApplyReport(status=ReportStatus.SUCCEEDED, manifest=plan.manifest, plan=plan)

    monkeypatch.setattr(cli, "apply_install_plan", apply_install_plan)

    result = runner.invoke(app, ["install"])

    assert result.exit_code == 0, result.stderr
    assert len(seen_on_disk) == 1, "apply must run exactly once, after persistence"
    assert 'harnesses = ["claude-code"]' in seen_on_disk[0]
    assert config_home.read_text(encoding="utf-8") == seen_on_disk[0]


def test_interactive_install_prefills_the_wizard_from_the_default_manifest(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    config_home.parent.mkdir(parents=True)
    config_home.write_text(MANIFEST_TOML, encoding="utf-8")

    result = runner.invoke(app, ["install"])

    assert result.exit_code == 0, result.stderr
    assert calls["wizard"] == [manifest_state()]


def test_interactive_install_keeps_stdout_empty(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    result = runner.invoke(app, ["install"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "", "interactive mode writes human output to stderr only"


def test_cancelled_wizard_exits_nonzero_and_writes_no_managed_state(
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "run_wizard", lambda _initial: None)

    result = runner.invoke(app, ["install"])

    assert result.exit_code != 0
    assert not config_home.exists()
    assert calls["plan"] == []
    assert calls["apply"] == []
    assert command_runner.commands == []
    assert result.stdout == ""


# ─── Doctor (acceptance:153) ─────────────────────────────────────────────────


def test_doctor_emits_one_json_document_and_changes_no_state(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["doctor", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert set(document) == {"status", "manifest", "plan", "results"}
    assert document["status"] == "succeeded"
    assert calls["verify"] == [manifest_state()]
    assert calls["apply"] == []
    assert manifest.read_text(encoding="utf-8") == MANIFEST_TOML
    assert not config_home.exists()


def test_doctor_defaults_to_the_standard_manifest_path(
    config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    config_home.parent.mkdir(parents=True)
    config_home.write_text(MANIFEST_TOML, encoding="utf-8")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.stderr
    assert calls["verify"] == [manifest_state()]


def test_doctor_with_an_invalid_manifest_exits_nonzero_without_verifying(
    tmp_path: Path, config_home: Path, command_runner: RecordingRunner, calls: dict
) -> None:
    manifest = write_manifest(tmp_path, 'harnesses = ["codex"]\ncomponents = ["tilth"]\n')

    result = runner.invoke(app, ["doctor", "--config", str(manifest)])

    assert result.exit_code != 0
    assert calls["verify"] == []
    assert command_runner.commands == []
    assert result.stdout == ""


def test_doctor_reports_failure_with_a_nonzero_exit_code(
    tmp_path: Path,
    config_home: Path,
    command_runner: RecordingRunner,
    calls: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path)

    def failing_verify(state: DesiredState, _adapters: object, _runner: object) -> DoctorReport:
        plan = a_plan(state)
        return DoctorReport(
            status=ReportStatus.FAILED,
            manifest=state,
            plan=plan,
            results=(a_result(StepStatus.FAILED),),
        )

    monkeypatch.setattr(cli, "verify_desired_state", failing_verify)

    result = runner.invoke(app, ["doctor", "--config", str(manifest)])

    assert result.exit_code != 0
    assert json.loads(result.stdout)["status"] == "failed"


# ─── Timeout plumbing ────────────────────────────────────────────────────────


@pytest.fixture
def built_timeouts(monkeypatch: pytest.MonkeyPatch) -> list[float | None]:
    """Record the ``timeout`` every ``SubprocessRunner`` the CLI builds receives."""
    recorded: list[float | None] = []

    class TimeoutRecordingRunner(RecordingRunner):
        def __init__(self, *, env: object = None, timeout: float | None = None) -> None:
            super().__init__()
            recorded.append(timeout)

    monkeypatch.setattr(cli, "SubprocessRunner", TimeoutRecordingRunner)
    monkeypatch.setattr(cli, "default_component_adapters", lambda _runner: {})
    return recorded


@pytest.mark.parametrize("command", ["install", "doctor"])
def test_the_timeout_option_reaches_the_subprocess_runner(
    tmp_path: Path,
    config_home: Path,
    calls: dict,
    built_timeouts: list[float | None],
    command: str,
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, [command, "--config", str(manifest), "--timeout", "12.5"])

    assert result.exit_code == 0, result.stderr
    assert built_timeouts == [12.5]


def test_without_the_timeout_option_the_runner_gets_the_package_default(
    tmp_path: Path, config_home: Path, calls: dict, built_timeouts: list[float | None]
) -> None:
    manifest = write_manifest(tmp_path)

    result = runner.invoke(app, ["install", "--config", str(manifest)])

    assert result.exit_code == 0, result.stderr
    assert built_timeouts == [DEFAULT_TIMEOUT_SECONDS]
