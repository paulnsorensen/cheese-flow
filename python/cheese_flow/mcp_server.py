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
from milknado._mcp_core import open_graph
from milknado._mcp_core import resolve_project_root as resolve_milknado_root
from milknado.domains.batching import (
    BatchPlan,
    FileChange,
    NewRelationship,
    SymbolRef,
    plan_batches,
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


MAX_SUMMARY_DESCRIPTION_LENGTH = 120

_VALID_REASONS = frozenset({"new_file", "new_import", "new_call", "new_type_use"})


def _require_str(d: dict, field: str) -> str:
    value = d.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field!r} must be a non-empty string, got {value!r}")
    return value


def _dict_to_file_change(d: dict) -> FileChange:
    _id = _require_str(d, "id")
    path = _require_str(d, "path")
    symbols = [
        SymbolRef(name=_require_str(s, "name"), file=_require_str(s, "file"))
        for s in d.get("symbols") or []
    ]
    return FileChange(
        id=_id,
        path=path,
        edit_kind=d.get("edit_kind", "modify"),
        symbols=tuple(symbols),
        depends_on=tuple(d.get("depends_on") or []),
    )


def _dict_to_new_relationship(d: dict) -> NewRelationship:
    reason = _require_str(d, "reason")
    if reason not in _VALID_REASONS:
        raise ValueError(f"invalid reason: {reason!r}; expected one of {sorted(_VALID_REASONS)}")
    return NewRelationship(
        source_change_id=_require_str(d, "source_change_id"),
        dependant_change_id=_require_str(d, "dependant_change_id"),
        reason=reason,
    )


def _plan_to_dict(plan: BatchPlan) -> dict:
    return {
        "batches": [
            {
                "index": b.index,
                "change_ids": list(b.change_ids),
                "depends_on": list(b.depends_on),
                "oversized": b.oversized,
            }
            for b in plan.batches
        ],
        "spread_report": [
            {"symbol": {"name": ss.symbol.name, "file": ss.symbol.file}, "spread": ss.spread}
            for ss in plan.spread_report
        ],
        "solver_status": plan.solver_status,
    }


@mcp.tool()
def milknado_graph_summary(project_root: str = "") -> str:
    """Return Mikado nodes (id, status, description) for the given project.

    Args:
        project_root: Absolute path to the project. Defaults to cwd or
            ``MILKNADO_PROJECT_ROOT`` environment variable.
    """
    root = resolve_milknado_root(project_root or None)
    graph, _cfg = open_graph(root)
    try:
        nodes = graph.get_all_nodes()
        if not nodes:
            return "(empty graph)"
        return "\n".join(
            f"id={node.id} status={node.status.value} "
            f"description={node.description[:MAX_SUMMARY_DESCRIPTION_LENGTH]!r}"
            for node in nodes
        )
    finally:
        graph.close()


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
    graph, _cfg = open_graph(root)
    try:
        node = graph.add_node(description, parent_id=parent_id)
        return f"created node id={node.id} description={node.description!r}"
    finally:
        graph.close()


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
        budget: Token budget per batch (default 70 000).
        new_relationships: Optional list of additional dependency edges to
            inject, each with source_change_id, dependant_change_id, and
            reason.
    """
    file_changes = [_dict_to_file_change(c) for c in changes]
    rels = tuple(_dict_to_new_relationship(r) for r in (new_relationships or []))
    plan = plan_batches(file_changes, budget, new_relationships=rels)
    return _plan_to_dict(plan)


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
