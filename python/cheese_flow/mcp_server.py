"""Unified FastMCP server for cheese-flow.

A single ``FastMCP("cheese-flow")`` instance exposes both the cheese-flow
tools (``cheese_*`` prefix) and the milknado tools (``milknado_*`` prefix).
Per US-015 / spec Pattern 1, FastMCP has no built-in prefix argument; the
prefix is the function name. ``cheese mcp`` calls :func:`run` which blocks
on ``mcp.run(transport="stdio")``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from milknado.config import project_root as resolve_milknado_root
from milknado.domains.graph import add_node as milknado_add_node_impl
from milknado.domains.graph import graph_summary as milknado_graph_summary_impl
from milknado.domains.planning import (
    dict_to_file_change,
    dict_to_new_relationship,
    plan_batches_stub,
    plan_to_dict,
)

from cheese_flow.adapters import HARNESS_NAMES
from cheese_flow.lib.compiler import compile_harness_bundles
from cheese_flow.lib.doctor import format_report, run_all_tool_checks
from cheese_flow.lib.harness import HarnessName
from cheese_flow.lib.install_plan import dedupe_harness_names, parse_harness_overrides
from cheese_flow.lib.installer import format_install_report, install_harnesses
from cheese_flow.lib.lint_skills import format_lint_report, lint_skills_directory

mcp = FastMCP(
    "cheese-flow",
    instructions=(
        "cheese-flow MCP server. Cheese-flow tools use the cheese_ prefix; "
        "milknado tools use the milknado_ prefix. Run cheese-flow housekeeping "
        "with cheese_doctor; emit harness bundles with cheese_compile; lint "
        "skills with cheese_lint. Mikado graph tools (graph_summary, add_node) "
        "operate on the project rooted at MILKNADO_PROJECT_ROOT or cwd."
    ),
)


def _resolve_targets(harness: list[str] | None) -> list[HarnessName]:
    if not harness:
        return list(HARNESS_NAMES)
    return dedupe_harness_names(parse_harness_overrides(harness))


@mcp.tool()
def cheese_doctor() -> str:
    """Verify required, recommended, and suggested CLI tools are installed."""
    results = asyncio.run(run_all_tool_checks())
    return format_report(results)


@mcp.tool()
def cheese_compile(
    project_root: str,
    harness: list[str] | None = None,
) -> list[str]:
    """Emit harness bundles from the repository skill and agent sources.

    Args:
        project_root: Project root that contains ./agents and ./skills.
        harness: Harness names to emit. Defaults to all supported harnesses.
    """
    targets = _resolve_targets(harness)
    return asyncio.run(compile_harness_bundles(project_root=project_root, harnesses=targets))


@mcp.tool()
def cheese_install(
    project_root: str,
    harness: list[str] | None = None,
) -> str:
    """Compile and install harness bundles into the local workspace.

    Args:
        project_root: Project root that contains ./agents and ./skills.
        harness: Harness names to install. Defaults to auto-detect.
    """
    requested = dedupe_harness_names(parse_harness_overrides(harness or []))
    report = asyncio.run(
        install_harnesses(
            project_root=project_root,
            requested_harnesses=requested,
        )
    )
    return format_install_report(report)


@mcp.tool()
def cheese_lint(project_root: str) -> str:
    """Lint skills/ against the Agent Skills format.

    Args:
        project_root: Project root that contains ./skills.
    """
    skills_dir = Path(project_root) / "skills"
    report = asyncio.run(lint_skills_directory(str(skills_dir)))
    return format_lint_report(report)


@mcp.tool()
def milknado_graph_summary(project_root: str = "") -> str:
    """Return Mikado nodes (id, status, description) for the given project.

    Args:
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
    """
    root = resolve_milknado_root(project_root or None)
    return milknado_graph_summary_impl(root)


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
    root = resolve_milknado_root(project_root or None)
    return milknado_add_node_impl(description, parent_id, root)


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


def run() -> None:
    """Block on the FastMCP stdio loop; called by the ``cheese mcp`` CLI."""
    mcp.run(transport="stdio")


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
