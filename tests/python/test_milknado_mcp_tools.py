"""Smoke tests for the milknado MCP tool surface (mcp_server.py)."""

from __future__ import annotations

import pytest
from mcp_server import (
    milknado_add_node,
    milknado_graph_summary,
    milknado_plan_batches,
)


def _call(tool, **kwargs):
    """FastMCP wraps tool callables; reach through ``.fn`` if present."""
    fn = getattr(tool, "fn", tool)
    return fn(**kwargs)


def test_mcp_plan_batches_validates_inputs() -> None:
    with pytest.raises(ValueError, match="repo-relative"):
        _call(
            milknado_plan_batches,
            changes=[{"id": "c1", "path": "../bad", "edit_kind": "modify"}],
        )
    result = _call(
        milknado_plan_batches,
        changes=[{"id": "c1", "path": "src/ok.py", "edit_kind": "modify"}],
    )
    assert result["solver_status"] == "STUB"
    assert result["batches"][0]["change_ids"] == ["c1"]


def test_mcp_graph_summary_returns_empty_string() -> None:
    assert _call(milknado_graph_summary) == "(empty graph)"


def test_mcp_add_node_returns_stub_marker() -> None:
    out = _call(milknado_add_node, description="ship the milknado solver")
    assert out.startswith("(stub)")
    assert "ship the milknado solver" in out
