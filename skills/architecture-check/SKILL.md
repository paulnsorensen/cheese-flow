---
name: architecture-check
description: Verify Sliced Bread architectural boundaries using the code-review-graph knowledge graph. Use when asked to check architecture, verify boundaries, find cross-slice imports, or audit module dependencies.
argument-hint: "[module-or-path]"
allowed-tools:
  - mcp__plugin_code-review-graph_code-review-graph__query_graph_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_architecture_overview_tool
  - mcp__plugin_code-review-graph_code-review-graph__list_communities_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_community_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_impact_radius_tool
  - mcp__plugin_code-review-graph_code-review-graph__list_graph_stats_tool
  - Read
  - Grep
  - Glob
---

# Architecture Check

Verify that the codebase follows Sliced Bread architectural boundaries using the code-review-graph knowledge graph.

## Prerequisites

The knowledge graph must be built first. Call `list_graph_stats_tool` to check. If no graph exists, tell the user to run `/code-review-graph:build-graph` first.

## Steps

1. **Load the architecture overview** by calling `get_architecture_overview_tool`. This gives you the high-level module structure, key files, and dependency patterns.

2. **Identify domain slices** by calling `list_communities_tool`. Each community roughly maps to a domain slice. For each community, call `get_community_tool` to get its members and cross-community edges.

3. **Check Sliced Bread rules** against the graph data:

   - **Crust violations**: Look for imports that bypass a slice's index/barrel file. External code should only import from `index.*` files, never from internal modules.
   - **Cross-slice reach-ins**: Find edges where module A in slice X imports directly from module B in slice Y (not through Y's index).
   - **Common leaf rule**: Verify that `common/` (or shared kernel) does not import from any sibling slice.
   - **Model purity**: Check that domain model files have no imports from adapters, frameworks, or infrastructure.
   - **Direction violations**: Look for circular dependencies between slices (use `query_graph_tool` with import edges).

4. **If a specific module or path was provided as argument**, narrow the analysis:
   - Call `get_impact_radius_tool` on the target to see its dependency web.
   - Focus boundary checks on that module's slice and its neighbors.

5. **Report findings** as a table:

   ```
   | Violation | Source | Target | Rule |
   |-----------|--------|--------|------|
   | Cross-slice reach-in | orders/fulfillment.py | pricing/calculator.py | Import from index only |
   | Model impurity | orders/order.py | adapters/db.py | Models stay pure |
   ```

   Include a summary: total violations, severity distribution, and which slices are cleanest/messiest.

## What This Does NOT Do

- Does not modify code. This is analysis only.
- Does not build the graph. Requires an existing graph.
- Does not check code style or formatting.
