"""Subprocess-backed :class:`~cheese_flow.models.CommandRunner`.

Everything cheese-flow shells out to — version resolution, native install
commands, and postcondition probes — goes through this runner, so apply and
doctor never touch :mod:`subprocess` themselves. The runner tracks the child it
is currently waiting on so the apply scheduler can forward SIGINT/SIGTERM to it.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from cheese_flow.models import CommandOutcome

MISSING_EXECUTABLE_EXIT_CODE = 127
"""Exit code reported when the child could not be started at all."""


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

    def __init__(self, *, env: Mapping[str, str] | None = None) -> None:
        self._env = dict(env) if env else None
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
            stdout, stderr = process.communicate()
        finally:
            with self._lock:
                self._active = None
        return CommandOutcome(
            argv=command,
            exit_code=process.returncode,
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
        try:
            process.send_signal(signum)
        except (ProcessLookupError, OSError):
            return

    def _environment(self) -> dict[str, str] | None:
        return {**os.environ, **self._env} if self._env else None


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
