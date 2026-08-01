"""Subprocess-backed :class:`~cheese_flow.models.CommandRunner`.

Everything cheese-flow shells out to — version resolution, native install
commands, and postcondition probes — goes through this runner, so apply and
doctor never touch :mod:`subprocess` themselves. The runner tracks the child it
is currently waiting on so the apply scheduler can forward SIGINT/SIGTERM to it.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from cheese_flow.models import CommandOutcome

MISSING_EXECUTABLE_EXIT_CODE = 127
"""Exit code reported when the child could not be started at all."""

TIMEOUT_EXIT_CODE = 124
"""Exit code reported when the child outlived its timeout and was killed."""

DEFAULT_TIMEOUT_SECONDS = 900.0
"""Wall clock a single child gets before it is killed, so a run cannot hang."""


@runtime_checkable
class SignalForwardingRunner(Protocol):
    """A runner that can pass a received signal on to the child it is running."""

    def forward_signal(self, signum: int) -> None:
        """Send ``signum`` to the active child, if there is one."""
        ...


class SubprocessRunner:
    """Runs child processes, capturing output and never raising on failure.

    ``env`` overlays the inherited environment, which is how a dry-run points
    npm at a throwaway metadata cache without leaking that setting into the
    parent process.
    """

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._env = dict(env) if env else None
        self._timeout = timeout
        self._lock = threading.Lock()
        self._active: subprocess.Popen[str] | None = None

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        """Run ``argv`` to completion and return its outcome."""
        command = tuple(argv)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=self._environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Its own process group, so a timeout can kill the whole tree.
                # Killing only the child leaves grandchildren holding the pipes.
                start_new_session=True,
            )
        except OSError as error:
            return CommandOutcome(
                argv=command,
                exit_code=MISSING_EXECUTABLE_EXIT_CODE,
                stdout="",
                stderr=f"could not run {command[0]}: {error.strerror or error}",
                elapsed_ms=_elapsed_ms(started),
            )
        with self._lock:
            self._active = process
        try:
            stdout, stderr = process.communicate(timeout=self._timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            # A wedged `npm install -g` or `hallouminate index` must not stall
            # the whole run: kill it and report the timeout as its outcome.
            _kill_group(process)
            try:
                stdout, stderr = process.communicate(timeout=_KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired as abandoned:
                # Whatever the child managed to say is the only evidence of why
                # it wedged, so keep it rather than reporting an empty capture.
                second_out, second_err = _partial(abandoned)
                stdout = second_out
                stderr = second_err
            exit_code = TIMEOUT_EXIT_CODE
            note = f"{command[0]} timed out after {self._timeout}s and was killed"
            stderr = f"{stderr}\n{note}" if stderr else note
        finally:
            with self._lock:
                self._active = None
            _reap(process)
        return CommandOutcome(
            argv=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            elapsed_ms=_elapsed_ms(started),
        )

    def forward_signal(self, signum: int) -> None:
        """Send ``signum`` to the child currently being waited on, if any."""
        with self._lock:
            process = self._active
        if process is None or process.poll() is not None:
            return
        # The child runs in its own session, so it shares no process group with
        # the terminal: nothing reaches its descendants unless we signal the
        # whole group. Killing only the direct child leaves an `npm install -g`
        # tree running after the run reports itself interrupted.
        try:
            os.killpg(os.getpgid(process.pid), signum)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.send_signal(signum)
            except (ProcessLookupError, OSError):
                return

    def _environment(self) -> dict[str, str] | None:
        return {**os.environ, **self._env} if self._env else None


_KILL_GRACE_SECONDS = 5.0
"""How long the killed process tree gets to close its pipes before we give up."""


def _partial(expired: subprocess.TimeoutExpired) -> tuple[str, str]:
    """Return whatever the timed-out child had already written.

    ``communicate`` accumulates raw chunks across calls and hands them back on
    the exception, so a timeout does not have to mean an empty capture.
    """
    return _decode(expired.stdout), _decode(expired.stderr)


def _decode(value: bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("utf-8", "replace")


def _reap(process: subprocess.Popen[str]) -> None:
    """Close the child's pipes and collect it, so no run leaks a fd or a zombie."""
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=0)


def _kill_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        process.kill()


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
