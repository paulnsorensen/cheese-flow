---
name: milknado-plan
description: Use the Milknado MCP tools to decompose a goal into a Mikado-style change graph and produce a token-budgeted batch plan.
license: MIT
compatibility: Requires the milknado MCP server to be configured and running.
allowed-tools:
  - read
  - mcp__milknado__milknado_graph_summary
  - mcp__milknado__milknado_add_node
  - mcp__milknado__milknado_plan_batches
---
# Milknado Plan

Use this skill to turn a high-level goal into a structured Mikado execution plan
backed by the Milknado graph. The skill calls the Milknado MCP server to inspect
the current graph state, decompose the goal into fine-grained changes, and
persist each change as a graph node.

## When to use
- Starting a new feature, refactor, or bug fix that touches multiple files.
- Resuming an interrupted plan (add delta nodes without recreating existing ones).
- Validating that a set of proposed changes can be batched within a token budget.

## Steps

1. **Inspect the graph** — call `milknado_graph_summary` to check for existing
   nodes. If nodes exist, operate in resuming mode.
2. **Read context** — read the relevant source files, spec documents, or issue
   descriptions needed to understand the goal.
3. **Decompose** — produce a v2 change manifest: file-level changes with
   `id`, `path`, `edit_kind`, `description`, `symbols`, and `depends_on`.
4. **Validate batches** — call `milknado_plan_batches` with the manifest to
   confirm the solver produces a feasible batch plan.
5. **Persist nodes** — call `milknado_add_node` for each change, linking
   prerequisite relationships via `parent_id`.
6. **Summarise** — report the number of nodes created, batch count, and any
   oversized or infeasible batches that need attention.

## Milknado MCP tools

| Tool | Purpose |
|---|---|
| `milknado_graph_summary` | Read the current graph (id, status, description per node). |
| `milknado_add_node` | Add a new work node, optionally linked to a parent. |
| `milknado_plan_batches` | Compute token-budgeted, precedence-respecting batches. |

## Manifest v2 quick reference

```json
{
  "manifest_version": "milknado.plan.v2",
  "goal": "Short goal statement",
  "goal_summary": "What / why / success criteria (2–4 sentences).",
  "changes": [
    {
      "id": "c1",
      "path": "src/example.py",
      "edit_kind": "modify",
      "description": "Causal description referencing the goal.",
      "symbols": [{"name": "ExampleClass", "file": "src/example.py"}],
      "depends_on": []
    }
  ]
}
```

**Closed `edit_kind` values:** `add`, `modify`, `delete`, `rename`
