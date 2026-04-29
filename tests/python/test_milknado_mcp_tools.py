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


def test_mcp_graph_summary_returns_empty_string(tmp_path) -> None:
    assert _call(milknado_graph_summary, project_root=str(tmp_path)) == "(empty graph)"


def test_mcp_add_node_returns_created_node(tmp_path) -> None:
    out = _call(
        milknado_add_node,
        description="ship the milknado solver",
        project_root=str(tmp_path),
    )
    assert out == "created node id=1 description='ship the milknado solver'"


def test_mcp_add_node_links_to_parent(tmp_path) -> None:
    parent = _call(
        milknado_add_node,
        description="parent node",
        project_root=str(tmp_path),
    )
    child = _call(
        milknado_add_node,
        description="child node",
        parent_id=1,
        project_root=str(tmp_path),
    )
    summary = _call(milknado_graph_summary, project_root=str(tmp_path))

    assert parent == "created node id=1 description='parent node'"
    assert child == "created node id=2 description='child node'"
    assert "id=1 status=pending description='parent node'" in summary
    assert "id=2 status=pending description='child node'" in summary
