"""Cheese-flow Python MCP server — milknado graph tools (stubbed).

Thin shim: validates inputs, delegates to ``milknado.*`` slices. The slices
are stubs until the real solver and sqlite graph back-end are pulled in from
``~/Dev/milknado``; replacing each stub does not change this file.
"""

from __future__ import annotations

# Upstream milknado uses the standalone ``fastmcp`` package; cheese-flow uses
# the FastMCP shipped inside the official ``mcp`` SDK. The class is the same.
from mcp.server.fastmcp import FastMCP
from milknado.config import project_root
from milknado.domains.graph import add_node_stub, graph_summary_stub
from milknado.domains.planning import (
    dict_to_file_change,
    dict_to_new_relationship,
    plan_batches_stub,
    plan_to_dict,
)

mcp = FastMCP(
    "milknado",
    instructions=(
        "Mikado graph tools: list nodes and add prerequisite nodes. "
        "Set MILKNADO_PROJECT_ROOT or pass project_root to target a repo."
    ),
)


@mcp.tool()
def milknado_graph_summary(project_root: str = "") -> str:
    """Return Mikado nodes (id, status, description) for the given project.

    Args:
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
    """
    root = _resolve_root(project_root)
    return graph_summary_stub(root)


@mcp.tool()
def milknado_add_node(
    description: str,
    parent_id: int | None = None,
    project_root: str = "",
) -> str:
    """Add a Mikado node; optional parent_id links a prerequisite edge.

    Args:
        description: Human-readable description of the work item.
        parent_id: Optional id of the parent node to link as a prerequisite.
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
    """
    root = _resolve_root(project_root)
    try:
        return add_node_stub(description, parent_id, root)
    except NotImplementedError:
        parent_info = f" parent={parent_id}" if parent_id is not None else ""
        return (
            f"(stub) milknado_add_node not yet wired; "
            f"would have created description={description!r}{parent_info}"
        )


@mcp.tool()
def milknado_plan_batches(
    changes: list[dict],
    budget: int = 70_000,
    new_relationships: list[dict] | None = None,
) -> dict:
    """Compute token-budgeted, precedence-respecting batches for changes.

    Args:
        changes: List of file-change dicts with keys id, path, edit_kind,
            symbols, and depends_on.
        budget: Token budget per batch (default 70 000). Currently unused by
            the stub.
        new_relationships: Optional list of additional dependency edges to
            inject, each with source_change_id, dependant_change_id, and
            reason.
    """
    file_changes = [dict_to_file_change(c) for c in changes]
    rels = tuple(dict_to_new_relationship(r) for r in (new_relationships or []))
    plan = plan_batches_stub(file_changes, budget, rels)
    return plan_to_dict(plan)


def _resolve_root(explicit: str):
    return project_root(explicit or None)


if __name__ == "__main__":
    mcp.run()
