---
name: cure
description: Finish what /age started. Loads both sidecars (fixes + suggestions), renders a unified stake table, gates on user approval, routes each approved item to the right handler (/cleanup or a cook sub-agent), then re-ages the touched paths up to a hard 3-turn cap.
license: MIT
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
# Cure — Finish what `/age` started

`/cure` is the *single* post-`/age` finisher. Where `/age` reviews and
emits sidecars, `/cure` consumes them, gates on the user, applies items
through the right handler, and re-ages the touched paths. In
cheesemaking, curing follows aging — the verb is exact.

The loop is intentional and bounded:

```
load → user gate → apply → re-age → (turn)
```

Nothing applies without explicit user approval. The re-age verify step
has a hard 3-turn cap per invocation.

## Arguments

```
/cure <slug>
```

`slug` is the same slug emitted by `/age`. `/cure` reads
`.cheese/age/<slug>.fixes.json` (required) and
`.cheese/age/<slug>.suggestions.json` (optional). See
`references/sources.md` for the resolution table and the
missing-sidecar error contract.

All harnesses share the project-root `.cheese/` runtime directory.

## Phase 1 — Load

Load `.cheese/age/<slug>.fixes.json` (required) and the optional
companion `.cheese/age/<slug>.suggestions.json`. Merge their items into
a single list. If the fixes file is missing, fail fast with the
missing-sidecar error documented in `references/sources.md`.

Fix items and suggestion items have different required keys:

- **Fix items** (`fixes.json`): `id`, `dimension`, `file`, `anchor`,
  `content`, `rationale`, `category`. All mechanically-applicable via
  `tilth_edit`.
- **Suggestion items** (`suggestions.json`): `id`, `dimension`, `file`,
  `outline_ref`, `narrative`, `agent_brief_for_cook`. No anchor or content;
  not mechanically-applicable.

## Phase 2 — User gate

Render the merged items as a stake-grouped table (high → medium → low),
sorted by file within each group:

```
| id | stake | category | dim | location | summary |
```

`stake` is not a stored field — derive it from `dimension` using the
fixed map: high (correctness, security, encapsulation, spec), medium
(complexity, deslop, assertions, nih), advisory (precedent). `category`
shows the sub-type for fix items (e.g. `deslop.swallowed_catch`) or
`suggestion` for suggestion items.

Items are already pre-classified by `/age`; `/cure` does not
re-classify. The default selection is **empty** — nothing applies on a
bare return. Recognized verbs:

```
1,3,5         (specific ids)
all-high      (every high-stake item)
none          (default; exit cleanly)
skip N        (drop item N from the change-order)
```

No item executes without an explicit selection. `/cure` always waits for
the user to pick ids; the orchestrator does not run on the user's behalf
and does not chain from `/age`.

## Phase 3 — Apply

Each approved item dispatches by **sidecar of origin** through the apply
router (see `references/apply-router.md`): `fixes.json` items route as
`edit`; `suggestions.json` items route as `suggestion`. The `category`
sub-type (e.g. `deslop.swallowed_catch`) is informational only.

| routing type | handler |
|---|---|
| `edit` | `/cleanup <slug>` (single-item synthesized sidecar) |
| `suggestion` | spawn one cook sub-agent per item with `agent_brief_for_cook` |

Cross-slice calls go through public skill entries only (`/cleanup`,
`/age`, `/cook`). No reaching into sibling internals.

For each applied item, record `touched_paths += item.file`.

## Phase 4 — Re-age

If any paths were touched, run internally:

```
/age --scope <touched_paths>
```

Diff the resulting `.cheese/age/<slug>.{fixes,suggestions}.json` against
the prior items and emit only **new or changed** items as the next
iteration. If empty, the loop exits cleanly.

If non-empty, ask the user whether to continue into the next turn. The
loop has a hard **3-turn cap** per invocation (`turn <= 3`, 1-indexed).
After turn 3, force-exit and surface remaining items as a one-line
"next session" hand-off the user can run as `/cure <slug>` again. See
`references/re-age.md` for the full diff semantics, the turn log, and
the cap rationale.

## Rules

- Default selection is empty. The user gate is the only path to apply.
- `/cure` is invoked manually after `/age` prints the hand-off; the
  orchestrator never chains it on the user's behalf.
- File I/O via `cheez-read` / `cheez-search` / `cheez-write`. No host
  `Read` / `Grep` / `Edit`. Sidecar JSON loads through `cheez-read`;
  direct edits use `cheez-write`. Hash-anchored fixes are owned by
  `/cleanup`, which calls `tilth_edit` natively.
- Cross-slice calls go through `/cleanup`, `/cook`, and `/age` only —
  no reaching into sibling internals.
- Re-age cap is 3 turns per invocation. After 3, hand off remaining
  items to the next invocation.

## References

- `references/sources.md` — sidecar paths and the missing-sidecar error
  contract.
- `references/apply-router.md` — routing-type → handler mapping.
- `references/re-age.md` — verify loop, diff semantics, 3-turn cap, turn
  log file.
