"""Top-level entry point — re-exports the unified ``cheese-flow`` MCP server.

The TS proxy spawns this file via ``uv run python python/mcp_server.py`` (until
US-017 deletes the proxy). Keeping the historical entry point alive while
delegating to :mod:`cheese_flow.mcp_server` lets the cutover be a pure delete
rather than a refactor.
"""

from __future__ import annotations

from cheese_flow.mcp_server import (
    cheese_compile,
    cheese_doctor,
    cheese_install,
    cheese_lint,
    mcp,
    milknado_add_node,
    milknado_graph_summary,
    milknado_plan_batches,
    run,
)

__all__ = [
    "cheese_compile",
    "cheese_doctor",
    "cheese_install",
    "cheese_lint",
    "mcp",
    "milknado_add_node",
    "milknado_graph_summary",
    "milknado_plan_batches",
    "run",
]


if __name__ == "__main__":
    run()
