"""Smoke tests for milknado.solve_blend_plan.

The LP has a closed-form optimal vertex, so we assert structure + the
specific optimum to catch regressions in solver wiring.
"""

from __future__ import annotations

import pytest

milknado = pytest.importorskip("milknado")


def test_solve_blend_plan_returns_expected_keys() -> None:
    result = milknado.solve_blend_plan()
    assert set(result.keys()) == {"status", "cheddar", "gouda", "objective"}


def test_solve_blend_plan_satisfies_constraints() -> None:
    result = milknado.solve_blend_plan()
    cheddar = float(result["cheddar"])
    gouda = float(result["gouda"])

    # cheddar + 2*gouda <= 14
    assert cheddar + 2 * gouda <= 14 + 1e-6
    # 3*cheddar - gouda >= 0
    assert 3 * cheddar - gouda >= -1e-6
    # cheddar - gouda <= 2
    assert cheddar - gouda <= 2 + 1e-6
    # objective = 3*cheddar + 4*gouda
    assert result["objective"] == pytest.approx(3 * cheddar + 4 * gouda, rel=1e-6)


def test_solve_blend_plan_reaches_known_optimum() -> None:
    # Optimum at (cheddar, gouda) = (6, 4): obj = 3*6 + 4*4 = 34.
    result = milknado.solve_blend_plan()
    assert result["objective"] == pytest.approx(34.0, rel=1e-6)
