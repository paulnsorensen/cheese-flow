"""Cheese-flow Python MCP server.

Exposes Python-side capabilities as MCP tools for a TypeScript MCP proxy to
forward. The proxy keeps this process alive across calls so each tool invocation
avoids a fresh ``uv run`` cold-start.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from milknado import solve_blend_plan

mcp = FastMCP("cheese-flow")


@mcp.tool()
def blend_plan() -> dict[str, Any]:
    """Solve the cheese blend plan LP via OR-Tools and return the raw result."""
    return solve_blend_plan()


if __name__ == "__main__":
    mcp.run()
