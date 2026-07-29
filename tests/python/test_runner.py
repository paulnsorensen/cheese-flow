"""Subprocess runner tests: real child processes, no mocked subprocess."""

from __future__ import annotations

import signal
import threading
import time
from pathlib import Path

from cheese_flow.runner import SubprocessRunner


def test_zero_exit_command_reports_exact_outcome() -> None:
    runner = SubprocessRunner()

    outcome = runner.run(("true",))

    assert outcome.argv == ("true",)
    assert outcome.exit_code == 0
    assert outcome.stdout == ""
    assert outcome.stderr == ""
    assert outcome.elapsed_ms >= 0


def test_nonzero_exit_is_returned_not_raised() -> None:
    outcome = SubprocessRunner().run(("false",))

    assert outcome.exit_code == 1
    assert outcome.stdout == ""


def test_stdout_stderr_and_exit_code_are_captured_separately() -> None:
    script = "printf brie; printf stink >&2; exit 3"

    outcome = SubprocessRunner().run(("sh", "-c", script))

    assert outcome.exit_code == 3
    assert outcome.stdout == "brie"
    assert outcome.stderr == "stink"


def test_cwd_is_applied_to_the_child(tmp_path: Path) -> None:
    outcome = SubprocessRunner().run(("pwd",), cwd=tmp_path)

    assert outcome.exit_code == 0
    assert Path(outcome.stdout.strip()) == tmp_path.resolve()


def test_missing_executable_becomes_a_failed_outcome() -> None:
    outcome = SubprocessRunner().run(("cheese-flow-definitely-not-a-command",))

    assert outcome.exit_code == 127
    assert outcome.stdout == ""
    assert "cheese-flow-definitely-not-a-command" in outcome.stderr


def test_env_overlay_adds_variables_without_dropping_the_inherited_environment() -> None:
    runner = SubprocessRunner(env={"CHEESE_TEST_VAR": "brie"})

    outcome = runner.run(("sh", "-c", 'printf "%s|%s" "$CHEESE_TEST_VAR" "${PATH:+set}"'))

    assert outcome.exit_code == 0
    assert outcome.stdout == "brie|set"


def test_forward_signal_without_an_active_child_is_a_no_op() -> None:
    runner = SubprocessRunner()

    runner.forward_signal(signal.SIGTERM)

    assert runner.run(("true",)).exit_code == 0


def test_forward_signal_terminates_the_active_child() -> None:
    runner = SubprocessRunner()
    outcomes: list[object] = []

    def run_child() -> None:
        outcomes.append(runner.run(("sh", "-c", "sleep 5")))

    worker = threading.Thread(target=run_child)
    worker.start()
    deadline = time.monotonic() + 5.0
    while worker.is_alive() and time.monotonic() < deadline:
        runner.forward_signal(signal.SIGTERM)
        time.sleep(0.02)
    worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.exit_code == -signal.SIGTERM  # type: ignore[attr-defined]
