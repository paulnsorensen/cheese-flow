"""Port of ``tests/package-scripts.test.ts``.

The TS test pinned the npm-era ``compile:all``/``install:all``/``install:auto``
scripts in ``package.json``. Per US-017 the entire ``package.json`` will be
deleted in the cutover; the equivalent surface is exposed as Typer
subcommands (``cheese compile``, ``cheese install``) and is already covered by
``tests/python/test_cli.py``. No assertions to port — keep the docstring as
the explicit skip rationale.
"""

from __future__ import annotations


def test_package_scripts_replaced_by_typer_cli() -> None:
    """Documents the skip — covered by test_cli.py."""
    # Intentionally a no-op: the npm scripts being asserted on no longer exist
    # in the Python distribution. The user-facing surface is now ``cheese
    # compile`` / ``cheese install`` and is exercised in ``test_cli.py``.
    assert True
