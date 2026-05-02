---
name: cleanup
description: Mechanical apply of /age's hash-anchored sidecar fixes via tilth_edit. The cleanup-wolf sub-agent is the only LLM in the path, fired per anchor mismatch.
license: MIT
compatibility: Requires Claude Code >= 2.1.30 / claude-agent-sdk >= 0.2.63 (tilth_edit must be exposed to plugin sub-agents).
metadata:
  owner: cheese-flow
  category: cleanup
allowed-tools:
  - read
  - write
  - bash
  - subagent
  - mcp
---
# Cleanup — Mechanical Fix Apply

Apply `/age` sidecar fixes mechanically via `tilth_edit`. No LLM in the
happy path. The `cleanup-wolf` sub-agent fires only on hash mismatch.

## Arguments

```
/cleanup <slug>
```

`slug` is the same slug produced by `/age`. Resolves to:

```
.cheese/age/<slug>.fixes.json
```

All harnesses share the project-root `.cheese/` runtime directory.

## Phase 1 — Load

Load `.cheese/age/<slug>.fixes.json`.

Validate schema: every entry must have all of
`id`, `dimension`, `file`, `anchor`, `content`, `rationale`, `category`.

If any entry fails validation, abort with a structured error listing the
invalid `id` values. Do not apply any fixes from a malformed file.

The validator is **additive** (v2): optional fields are tolerated. Any
extra keys beyond the v1 required set above — including
`pr_thread_id`, `review_body_id`, `reviewer`, `job_id`, `log_excerpt`,
and `conflicting_paths` — are accepted and ignored by `/cleanup`. The
required keys are not relaxed; the abort-on-missing behavior is
preserved. See `skills/affine/references/schema.md` for the v2 shape.

If the file does not exist, fail fast:

```
ERROR: .cheese/age/<slug>.fixes.json not found.
Run /age first to generate the fixes sidecar.
```

## Phase 2 — Apply Each Fix

For each fix in `fixes`:

```
try:
  tilth_edit(
    path=fix.file,
    edits=[{
      start: fix.anchor.start,
      end:   fix.anchor.end,
      content: fix.content
    }]
  )
  record: applied fix.id

except HashMismatch:
  spawn cleanup-wolf sub-agent with:
    fix              — the original fix entry
    current_file     — cheez-read(fix.file, section containing anchor lines)
    rationale        — fix.rationale

  record wolf result: {id, status: "applied"|"skip"|"already_applied", ...}
```

Hash mismatch is the ONLY trigger for `cleanup-wolf`. Every other path is
mechanical. Do not spawn the wolf for schema errors, missing files, or
any other condition.

**cleanup-wolf contract** (see `skills/cleanup/references/wolf-protocol.md`):

The wolf receives the fix entry and the current file state at the
affected region. It attempts to re-anchor via `cheez-search` narrative
match and applies with `tilth_edit`. Returns one of:

```json
{"id": "<fix.id>", "status": "applied", "new_anchor": {...}, "file": "..."}
{"id": "<fix.id>", "status": "skip", "reason": "<reason>"}
{"id": "<fix.id>", "status": "already_applied"}
```

## Phase 3 — Emit Report

Write `.cheese/age/<slug>.cleanup-report.md`:

```markdown
# Cleanup Report — <slug>

Applied:      <N> fixes
Wolf-rescued: <M> (hash mismatch, re-anchored and applied)
Skipped:      <K> (hash mismatch, wolf could not re-anchor)

## Skipped Details
<id> — <reason>
```

If all fixes were applied cleanly (zero wolf invocations), omit the
Wolf-rescued and Skipped rows.

Print the report path to the caller.

## Rules

- `cleanup-wolf` is the only LLM in this skill. The happy path has zero
  agent spawns.
- Do not modify `<slug>.fixes.json` or `<slug>.suggestions.json`.
- Do not apply suggestions. `/cleanup` is fixes-only; suggestions flow to
  `/fromage cook`.
- `tilth_edit` hash validation is the source of truth for anchor
  correctness. Do not second-guess it.
- Each fix is applied independently. A wolf failure on one fix does not
  block the remaining fixes.
