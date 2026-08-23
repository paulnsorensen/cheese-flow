"""A ``CliRunner`` for cyclopts apps, shaped like Typer's ``CliRunner``.

Cyclopts ships no test runner: an app is invoked by calling it with a token
list, and its default ``result_action`` turns every outcome — success, parse
error, ``--help`` — into a ``SystemExit``. This wrapper drives that call, pins a
wide non-tty console so Rich renders option names without wrapping, isolates
``os.environ``/``stdin`` per invocation, and captures stdout and stderr into a
result object exposing the same ``exit_code``/``stdout``/``stderr``/``output``/
``exception`` surface the migrated tests already assert against.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from dataclasses import dataclass
from unittest import mock

from cyclopts import App


@dataclass(frozen=True)
class Result:
    """The outcome of one CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str
    exception: BaseException | None

    @property
    def output(self) -> str:
        """Combined stream, matching Typer's ``result.output``."""
        return self.stdout + self.stderr


class CliRunner:
    """Invoke a cyclopts ``App`` and collect its streams and exit code."""

    def invoke(
        self,
        app: App,
        args: list[str],
        *,
        input: str | None = None,
        env: dict[str, str] | None = None,
    ) -> Result:
        out, err = io.StringIO(), io.StringIO()
        # COLUMNS pins Rich's width so help panels never wrap an option name off
        # the line the substring assertions read; a live os.environ reference is
        # what Rich consults per render, so patch.dict reaches it.
        overlay = {"COLUMNS": "200", **(env or {})}
        exception: BaseException | None = None
        exit_code = 0
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            stack.enter_context(mock.patch.dict(os.environ, overlay))
            if input is not None:
                stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(input)))
            try:
                app(args)
            except SystemExit as exit_signal:
                exception = exit_signal
                code = exit_signal.code
                exit_code = 0 if code is None else code if isinstance(code, int) else 1
            except BaseException as error:  # noqa: BLE001 — mirror CliRunner: capture, don't raise
                exception = error
                exit_code = 1
        return Result(
            exit_code=exit_code, stdout=out.getvalue(), stderr=err.getvalue(), exception=exception
        )
