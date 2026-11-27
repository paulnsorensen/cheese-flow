---
name: impact-analysis
description: Analyze the blast radius of recent changes using the code-review-graph knowledge graph. Use when asked to check impact, assess risk of changes, find affected flows, or do pre-commit impact analysis.
argument-hint: "[file-or-module]"
allowed-tools:
  - mcp__plugin_code-review-graph_code-review-graph__detect_changes_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_impact_radius_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_affected_flows_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_review_context_tool
  - mcp__plugin_code-review-graph_code-review-graph__list_flows_tool
  - mcp__plugin_code-review-graph_code-review-graph__get_flow_tool
  - mcp__plugin_code-review-graph_code-review-graph__list_graph_stats_tool
  - Bash
  - Read
  - Grep
  - Glob
---

# Impact Analysis

Analyze the blast radius of staged or recent changes using the code-review-graph knowledge graph.

## Prerequisites

The knowledge graph must be built. Call `list_graph_stats_tool` to verify. If missing, tell the user to run `/code-review-graph:build-graph`.

## Steps

1. **Identify what changed**:
   - If a file or module was provided as argument, use that as the target.
   - Otherwise, call `detect_changes_tool` to find recently modified files.
   - If no changes detected, run `git diff --name-only HEAD` to get unstaged changes.

2. **For each changed file**, call `get_impact_radius_tool` to get:
   - Direct dependents (files that import from the changed file)
   - Transitive dependents (files affected indirectly)
   - Total blast radius count

3. **Check affected flows** by calling `get_affected_flows_tool` with the changed files. This shows which end-to-end execution paths are impacted.

4. **Get review context** by calling `get_review_context_tool` for the changes. This provides:
   - Related symbols and their roles
   - Suggested review focus areas
   - Cross-cutting concerns

5. **Risk assessment** — score each changed file:

   | Risk Level | Criteria |
   |------------|----------|
   | HIGH | Blast radius > 10 files, or touches a flow entry point |
   | MEDIUM | Blast radius 4-10 files, or touches shared utilities |
   | LOW | Blast radius <= 3 files, leaf node change |

6. **Report findings**:

   ```
   ## Impact Summary

   | File | Direct | Transitive | Risk | Affected Flows |
   |------|--------|------------|------|----------------|
   | src/orders/order.py | 5 | 12 | HIGH | checkout, fulfillment |

   ### Recommended Review Focus
   - [areas from review context]

   ### Test Coverage Gaps
   - [flows without obvious test coverage]
   ```

## What This Does NOT Do

- Does not modify code or fix issues.
- Does not run tests. Use `/test` for that.
- Does not build the graph.
