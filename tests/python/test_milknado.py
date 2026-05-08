"""Port of ``tests/milknado.test.ts``.

The TS file tested ``src/lib/milknado.ts`` — a TS bridge that built a
``uv run python python/milknado.py`` subprocess command, streamed stdout/stderr,
and translated child-process signals/exit codes into typed errors. Per US-015
that bridge is gone: the Python ``cheese milknado`` subcommand now invokes the
in-process ``blend_demo`` helper directly (see
``python/cheese_flow/cli.py::_run_milknado``), with no subprocess, no spawn
helper, and no signal translation layer to test.

Concretely:

- ``getMilknadoBackendScriptPath`` / ``getMilknadoCommand`` /
  ``runMilknadoCommand`` and the ``SpawnFn`` mock surface have no Python
  equivalents and never will — they were artefacts of the TS-to-Python
  proxy.
- The ``"wires up milknado help without requiring uv or Python"`` smoke is
  preserved as ``test_milknado_help_mentions_project_root`` in
  ``tests/python/test_cli.py``.

This file remains as the explicit, named skip required by US-016.
"""

from __future__ import annotations


def test_milknado_bridge_replaced_by_inprocess_blend_demo() -> None:
    """Documents the skip — see module docstring for rationale."""
    assert True
