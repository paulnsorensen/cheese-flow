# Tool-Scoping Dim — Protocol

The tool-scoping reviewer checks whether the target's `tools` allowlist,
any `disallowedTools`, and `skills:` declarations match its stated role
and behavioral footprint.

## Why this dim exists

Over-broad tool access degrades behavior in two ways:

1. **Token waste** — every declared tool burns budget on tool-decision
   noise even when never used.
2. **Irreversible-action drift** — when stuck, models reach for whatever
   is available. A read-only reviewer with `Edit` declared will edit
   when a prose-only constraint says it shouldn't.

Prose constraints ("this is a read-only agent") are weaker than structural
tool limits. In this repo, `tools` is an explicit allowlist; an allowlist
containing only read tools is sufficient. Use `disallowedTools` as a
defense-in-depth signal only when write tools are otherwise reachable or a
host grants broad defaults.

## Three-tier model

Every agent should fall into one of these tiers:

| Tier | `tools` | `disallowedTools` | Use case |
|---|---|---|---|
| Read-only | `tilth_read`, `tilth_search`, optional `bash` | only when host defaults expose write tools | Reviewers, auditors, explorers |
| Write-scoped | + `tilth_edit` | tighten to exclude unused | Implementers, fixers |
| Focused sub-agent | 2–4 tools max | none needed | Pipeline sub-tasks |

A target that does not fall cleanly into one tier likely has scope
creep; surface as `tool-scoping.tier_mismatch` with `bucket: med`.

## Failure modes (with examples)

### `tool-scoping.prose_only_readonly`

Body says "read-only" but write tools are reachable. Common in agents
cloned from a write-scoped template. Do not flag missing `disallowedTools`
when `tools` is an explicit read-only allowlist.

```yaml
# Bad
tools: [mcp__tilth__tilth_read, mcp__tilth__tilth_edit]
# Body: "You are a read-only reviewer."

# Good: explicit allowlist, no write tools reachable
tools: [mcp__tilth__tilth_read]

# Also good when the host grants broad defaults
tools: [mcp__tilth__tilth_read]
disallowedTools: [Edit, Write, NotebookEdit]
```

### `tool-scoping.over_broad_tools`

Focused sub-agent declares 8+ tools when 2–3 would suffice. Each
declared tool burns context.

### `tool-scoping.skill_delegation_gap`

Agent body uses a skill that's not in `skills:`, or declares a skill
it never invokes.

```yaml
# Bad
skills: [cheez-read]
# Body: uses cheez-search heavily

# Good
skills: [cheez-read, cheez-search]
```

### `tool-scoping.wrong_namespace`

Plain tool names instead of MCP namespaces. The host won't expose
`Read` to plugin sub-agents — must use `mcp__tilth__tilth_read`.

```yaml
# Bad
tools: [Read, Grep]

# Good
tools:
  - mcp__tilth__tilth_read
  - mcp__tilth__tilth_search
```

### `tool-scoping.stale_disallowed`

`disallowedTools` lists a tool that no longer exists in the platform.
Lint-only, but signals stale config.

## Stake calibration

| Defect | Default bucket |
|---|---|
| `prose_only_readonly` with a reachable write tool | `high` |
| `wrong_namespace` (host won't expose) | `high` |
| `over_broad_tools` (cosmetic) | `med` |
| `skill_delegation_gap` (false positive likely) | `med` |
| `stale_disallowed` | `low` |

## What this dim does NOT do

- Does not evaluate the description copy — that's activation.
- Does not evaluate prompt body — that's prompt-quality.
- Does not evaluate output schema — that's output-format.
