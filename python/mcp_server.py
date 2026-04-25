"""Cheese-flow Python MCP server — Milknado graph tools (stubbed).

Exposes Milknado graph capabilities as MCP tools for a TypeScript MCP proxy to
forward. The proxy keeps this process alive across calls so each tool invocation
avoids a fresh ``uv run`` cold-start.

These tool implementations are stubs: they expose the correct MCP interface so
harnesses and agents can call them, but return placeholder data until the full
Milknado graph back-end is wired in.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("milknado")


@mcp.tool()
def milknado_graph_summary(project_root: str = "") -> str:
    """Return Mikado nodes (id, status, description) for the given project.

    Args:
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
    """
    return "(stub: empty graph — milknado back-end not yet wired)"


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
    parent_info = f" parent={parent_id}" if parent_id is not None else ""
    return f"(stub) created node id=0 description={description!r}{parent_info}"


@mcp.tool()
def milknado_plan_batches(
    changes: list[dict],
    budget: int = 70_000,
    project_root: str = "",
    new_relationships: list[dict] | None = None,
) -> dict:
    """Compute token-budgeted, precedence-respecting batches for changes.

    Args:
        changes: List of file-change dicts with keys id, path, edit_kind,
            symbols, and depends_on.
        budget: Token budget per batch (default 70 000).
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
        new_relationships: Optional list of additional dependency edges to
            inject, each with source_change_id, dependant_change_id, and reason.
    """
    change_ids = [c.get("id", str(i)) for i, c in enumerate(changes)]
    return {
        "batches": [
            {
                "index": 0,
                "change_ids": change_ids,
                "depends_on": [],
                "oversized": False,
            }
        ],
        "spread_report": [],
        "solver_status": "STUB",
    }


if __name__ == "__main__":
    mcp.run()
