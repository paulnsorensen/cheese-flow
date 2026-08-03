"""Subprocess runner tests: real child processes, no mocked subprocess."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from cheese_flow import runner as runner_module
from cheese_flow.runner import TIMEOUT_EXIT_CODE, SubprocessRunner


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


@contextlib.contextmanager
def readable_stdin(content: bytes) -> Iterator[None]:
    """Give this process a stdin holding ``content``, then hand it back.

    Asserting a child cannot reach the parent's stdin needs a parent stdin
    worth reaching. Under pytest fd 0 is already spent, so a child that
    inherits it sees the same EOF the fix produces and the assertion proves
    nothing. The write end closes before the child starts, so a leak shows up
    as content rather than as a hung test.
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, content)
    os.close(write_fd)
    saved = os.dup(0)
    try:
        os.dup2(read_fd, 0)
        os.close(read_fd)
        yield
    finally:
        os.dup2(saved, 0)
        os.close(saved)


def test_a_child_cannot_read_the_parents_stdin() -> None:
    """Nothing cheese-flow runs is interactive, and the runner must enforce that.

    With stdin inherited, a plugin CLI asking to trust a source or an installer
    confirming a scope holds the terminal until the timeout kills it — 15
    minutes per step by default, with no progress output naming the step that
    is stuck.
    """
    runner = SubprocessRunner(timeout=5.0)

    with readable_stdin(b"leaked\n"):
        outcome = runner.run(("cat",))

    assert outcome.exit_code == 0
    assert outcome.stdout == "", "the child read the parent's stdin"


def test_a_child_prompting_for_input_fails_fast_instead_of_waiting() -> None:
    """The shape of the real failure: the prompt gets EOF and the step reports it."""
    runner = SubprocessRunner(timeout=5.0)

    with readable_stdin(b"yes\n"):
        outcome = runner.run(("sh", "-c", 'printf "trust this source? " >&2; read answer'))

    assert outcome.exit_code != 0
    assert outcome.exit_code != TIMEOUT_EXIT_CODE
    assert "trust this source?" in outcome.stderr


def test_forward_signal_without_an_active_child_is_a_no_op() -> None:
    runner = SubprocessRunner()

    runner.forward_signal(signal.SIGTERM)

    assert runner.run(("true",)).exit_code == 0


def test_a_hanging_child_is_killed_and_reported_rather_than_stalling_the_run() -> None:
    runner = SubprocessRunner(timeout=0.2)
    started = time.monotonic()

    outcome = runner.run(("sh", "-c", "sleep 30"))

    assert time.monotonic() - started < 10.0
    assert outcome.exit_code == TIMEOUT_EXIT_CODE
    assert "0.2" in outcome.stderr
    assert "timed out" in outcome.stderr


def test_output_produced_before_the_timeout_is_still_captured() -> None:
    runner = SubprocessRunner(timeout=0.3)

    outcome = runner.run(("sh", "-c", "printf brie; printf stink >&2; sleep 30"))

    assert outcome.exit_code == TIMEOUT_EXIT_CODE
    assert outcome.stdout == "brie"
    assert "stink" in outcome.stderr


def test_a_child_finishing_inside_the_timeout_reports_its_own_outcome() -> None:
    outcome = SubprocessRunner(timeout=30.0).run(("sh", "-c", "printf brie; exit 3"))

    assert outcome.exit_code == 3
    assert outcome.stdout == "brie"


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


def _group_is_gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


def _await_active_pid(runner: SubprocessRunner) -> int:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        process = runner._active  # noqa: SLF001 — the pid has no public accessor
        if process is not None:
            return process.pid
        time.sleep(0.01)
    raise AssertionError("the runner never reported an active child")


def test_drained_output_survives_a_child_that_never_closes_its_pipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grandchild in its own session outlives the kill and holds stdout open.

    ``killpg`` cannot reach it, so the post-kill ``communicate`` times out too.
    Whatever the child managed to say before the timeout is the only evidence of
    why it wedged, so it must survive rather than be replaced by an empty read.
    """
    monkeypatch.setattr(runner_module, "_KILL_GRACE_SECONDS", 0.5)
    runner = SubprocessRunner(timeout=0.3)

    outcome = runner.run(("sh", "-c", "setsid sleep 5 & printf brie; printf stink >&2; sleep 30"))

    assert outcome.exit_code == TIMEOUT_EXIT_CODE
    assert outcome.stdout == "brie"
    assert "stink" in outcome.stderr
    assert "timed out" in outcome.stderr


def test_forward_signal_kills_the_grandchildren_too() -> None:
    """The child runs in its own session, so only signalling the group reaches
    its descendants; killing the direct child alone leaves the tree running."""
    runner = SubprocessRunner()
    outcomes: list[object] = []

    def run_child() -> None:
        outcomes.append(runner.run(("sh", "-c", "sleep 30 & wait")))

    worker = threading.Thread(target=run_child)
    worker.start()
    try:
        pgid = os.getpgid(_await_active_pid(runner))
        deadline = time.monotonic() + 5.0
        while worker.is_alive() and time.monotonic() < deadline:
            runner.forward_signal(signal.SIGTERM)
            time.sleep(0.02)
    finally:
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert len(outcomes) == 1
    deadline = time.monotonic() + 5.0
    while not _group_is_gone(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _group_is_gone(pgid), "the backgrounded grandchild outlived the forwarded signal"


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="requires Linux procfs")
def test_every_child_is_reaped_leaving_no_zombie_and_no_leaked_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_reap`` closes the pipes and collects the child, so a long run neither
    exhausts the descriptor table nor accumulates zombies."""
    pids: list[int] = []
    real_popen = subprocess.Popen

    def spy(*args: object, **kwargs: object) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)  # type: ignore[arg-type]
        pids.append(process.pid)
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", spy)
    runner = SubprocessRunner()
    open_fds = Path("/proc/self/fd")
    before = len(list(open_fds.iterdir()))

    for _ in range(25):
        assert runner.run(("true",)).exit_code == 0

    assert len(pids) == 25
    assert len(list(open_fds.iterdir())) <= before
    assert [pid for pid in pids if _process_state(pid) == "Z"] == []


def _process_state(pid: int) -> str | None:
    """The Linux scheduler state letter for ``pid``, or ``None`` once it is gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return stat.rpartition(")")[2].split()[0]
