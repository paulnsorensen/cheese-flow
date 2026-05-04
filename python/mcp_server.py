"""Cheese-flow MCP server entry point.

`cheese mcp` invokes this file via `npx tsx src/index.ts mcp` (see
`src/lib/mcp-proxy.ts`). The actual tool surface lives at
`milknado.mcp_server`; this module re-exports it so the harness can spawn it
with `python python/mcp_server.py`.
"""

from __future__ import annotations

from milknado.mcp_server import main, mcp

__all__ = ["main", "mcp"]


if __name__ == "__main__":
    main()
