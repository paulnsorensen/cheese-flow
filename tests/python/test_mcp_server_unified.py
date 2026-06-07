"""Tests for the unified ``cheese-flow`` FastMCP umbrella (``cheese_flow.mcp_server``).

Replaces the TS coverage in ``tests/mcp-proxy.test.ts``: per US-015 there is
no proxy — a single FastMCP instance exposes both ``cheese_*`` and
``milknado_*`` prefixed tools. The acceptance smoke test asserts that the
stdio MCP server ``cheese mcp`` reports both prefix sets via ``tools/list``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cheese_flow.mcp_server import mcp

REPO_ROOT = Path(__file__).resolve().parents[2]


def _list_tool_names() -> list[str]:
    tools = asyncio.run(mcp.list_tools())
    return [tool.name for tool in tools]


def test_unified_server_exposes_cheese_prefix_tools() -> None:
    names = _list_tool_names()
    cheese = [n for n in names if n.startswith("cheese_")]
    assert "cheese_doctor" in cheese
    assert "cheese_compile" in cheese
    assert "cheese_install" in cheese
    assert "cheese_lint" in cheese


def test_unified_server_exposes_milknado_prefix_tools() -> None:
    names = _list_tool_names()
    milknado = [n for n in names if n.startswith("milknado_")]
    assert "milknado_graph_summary" in milknado
    assert "milknado_add_node" in milknado
    assert "milknado_plan_batches" in milknado


def test_unified_server_has_no_unprefixed_tools() -> None:
    """FR-1: every tool MUST carry a domain prefix."""
    names = _list_tool_names()
    for name in names:
        assert name.startswith("cheese_") or name.startswith("milknado_"), name


def test_unified_server_name_is_cheese_flow() -> None:
    assert mcp.name == "cheese-flow"


def test_cheese_doctor_tool_executes_end_to_end() -> None:
    """One ``cheese_*`` tool executes and returns the doctor report."""
    from cheese_flow.mcp_server import cheese_doctor

    fn = getattr(cheese_doctor, "fn", cheese_doctor)
    output = fn()
    assert "cheese doctor — tool dependency check" in output


def test_milknado_plan_batches_tool_executes_end_to_end() -> None:
    """One ``milknado_*`` tool executes and returns a plan dict."""
    from cheese_flow.mcp_server import milknado_plan_batches

    fn = getattr(milknado_plan_batches, "fn", milknado_plan_batches)
    result = fn(
        changes=[{"id": "c1", "path": "src/ok.py", "edit_kind": "modify"}],
    )
    assert result["solver_status"] == "STUB"
    assert result["batches"][0]["change_ids"] == ["c1"]


def test_cheese_mcp_stdio_lists_both_prefix_sets() -> None:
    """End-to-end smoke: spawn ``cheese mcp`` and list tools over stdio JSON-RPC."""

    async def _run() -> list[str]:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "cheese",
            "mcp",
            cwd=str(REPO_ROOT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None

        async def send(payload: dict) -> None:
            assert proc.stdin is not None
            proc.stdin.write((json.dumps(payload) + "\n").encode())
            await proc.stdin.drain()

        async def recv() -> dict:
            assert proc.stdout is not None
            line = await proc.stdout.readline()
            return json.loads(line.decode())

        try:
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest-smoke", "version": "0"},
                    },
                }
            )
            init = await asyncio.wait_for(recv(), timeout=15)
            assert init.get("id") == 1, init

            await send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            listed = await asyncio.wait_for(recv(), timeout=15)
            return [t["name"] for t in listed["result"]["tools"]]
        finally:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()

    names = asyncio.run(_run())
    assert any(n.startswith("cheese_") for n in names), names
    assert any(n.startswith("milknado_") for n in names), names
