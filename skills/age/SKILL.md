---
name: age
description: Staff Engineer code review orchestrator. Runs eight orthogonal LLM dimensions (correctness, security, complexity, encapsulation, spec, precedent, deslop, assertions) over a diff and emits a stake-weighted report plus hash-anchored sidecar JSON consumed by /cleanup and /fromage cook.
license: MIT
compatibility: Requires Claude Code >= 2.1.30 / claude-agent-sdk >= 0.2.63 (older versions cannot expose tilth tools to plugin sub-agents).
metadata:
  owner: cheese-flow
  category: review
allowed-tools:
  - read
  - write
  - bash
  - subagent
  - mcp
---
# Age

Stub. Replaced by the orchestrator in wiring task W2.

This file exists to satisfy the cheese-flow compiler's SKILL.md requirement
while parallel atoms author the dim agents and references that the
orchestrator coordinates. See `.claude/specs/age-extraction.md` and
`.claude/fromagerie/age-extraction/manifest.json` for the active build plan.
