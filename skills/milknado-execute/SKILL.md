---
name: milknado-execute
description: Use the Milknado MCP tools to pick and execute the next ready node from the Mikado graph, apply file changes, and run quality gates.
license: MIT
compatibility: Requires the milknado MCP server to be configured and running.
allowed-tools:
  - read
  - write
  - bash
  - mcp__milknado__milknado_graph_summary
  - mcp__milknado__milknado_add_node
---
# Milknado Execute

Use this skill to work through a Milknado graph one node at a time. Each
invocation picks the next ready node, applies the required changes, validates
them with quality gates, and reports the outcome.

## When to use
- After `milknado-plan` has populated the graph with pending work nodes.
- To make incremental, reviewable progress on a multi-file change plan.
- To surface blockers that need to be captured as new prerequisite nodes.

## Steps

1. **Read the graph** — call `milknado_graph_summary` to find `pending` nodes
   whose prerequisites are all `done`. (Eligibility is computed by the engine;
   there is no stored `ready` status — the summary only shows the persisted
   `pending`/`running`/`done`/`blocked`/`failed` values.)
2. **Select a node** — use the provided node id, or pick the highest-priority
   eligible `pending` node. Read its description carefully — it is the primary context.
3. **Inspect files** — read all files relevant to the node before writing
   anything.
4. **Apply changes** — follow the `edit_kind` in the node description
   (`add`, `modify`, `delete`, or `rename`). Keep changes strictly scoped.
5. **Run quality gates** in order:
   - **Lint** — fix any lint errors introduced by the change.
   - **Typecheck** — resolve type errors.
   - **Tests** — run the relevant suite; never remove or skip existing tests.
6. **Report outcome:**
   - If gates pass: summarise what changed and confirm the node can be marked done.
   - If a blocker is found: call `milknado_add_node` to record it as a new
     prerequisite (with `parent_id` set to the current node), then leave the
     current node open for re-dispatch.

## Milknado MCP tools

| Tool | Purpose |
|---|---|
| `milknado_graph_summary` | Read the graph to find pending nodes whose prerequisites are done. |
| `milknado_add_node` | Record a newly discovered blocker as a prerequisite node. |

## Execution constraints
- One node per invocation — do not batch multiple nodes.
- Quality gates are mandatory — never skip or comment out failing tests.
- Do not refactor code outside the scope of the node description.
