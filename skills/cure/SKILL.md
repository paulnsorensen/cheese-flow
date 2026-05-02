---
name: cure
description: Finish what /age started. Loads both sidecars (fixes + suggestions), renders a unified stake table, gates on user approval, routes each approved item to the right handler (/cleanup, cook sub-agent, cheez-write, /merge-resolve, /cook), then re-ages the touched paths up to a hard 3-turn cap.
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

Nothing applies without explicit user approval. Replies are drafted to a
file, never sent. The re-age verify step has a hard 3-turn cap per
invocation.

## Arguments

```
/cure <slug>                  # auto-detect source (age first, then affine)
/cure <slug> --from age       # pin source to .cheese/age/<slug>.*
/cure <slug> --from affine    # pin source to .cheese/affine/<slug>.*
```

`slug` is the same slug emitted by `/age` or `/affine`. Source
disambiguates by directory: `.cheese/age/<slug>.fixes.json` (and
companion `<slug>.suggestions.json`) vs `.cheese/affine/<slug>.fixes.json`.
Auto-detect tries age first, then affine; explicit `--from` always
overrides. See `references/sources.md` for the full resolution table and
the missing-sidecar error contract.

All harnesses share the project-root `.cheese/` runtime directory.

## Phase 1 — Load

Resolve the source per the auto-detect order or the explicit `--from`
flag:

1. `--from age` → `.cheese/age/<slug>.*`
2. `--from affine` → `.cheese/affine/<slug>.*`
3. Auto-detect: try `.cheese/age/<slug>.fixes.json` first, then
   `.cheese/affine/<slug>.fixes.json`.

Load `<dir>/<slug>.fixes.json` (required) and the optional companion
`<dir>/<slug>.suggestions.json`. Merge their items into a single list.
If neither sidecar exists, fail fast with the missing-sidecar error
documented in `references/sources.md`.

Fix items and suggestion items have different required keys:

- **Fix items** (`fixes.json`): `id`, `dimension`, `file`, `anchor`,
  `content`, `rationale`, `category`. All mechanically-applicable via
  `tilth_edit`.
- **Suggestion items** (`suggestions.json`): `id`, `dimension`, `file`,
  `outline_ref`, `narrative`, `agent_brief_for_cook`. No anchor or content;
  not mechanically-applicable.

V2 optional fields (`pr_thread_id`, `review_body_id`, `reviewer`,
`job_id`, `log_excerpt`, `conflicting_paths`) are tolerated on either
item type and pass through to the apply router when relevant.

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

Items are already pre-classified by `/age` (or `/affine`); `/cure` does
not re-classify. The default selection is **empty** — nothing applies
on a bare return. Recognized verbs:

```
1,3,5         (specific ids)
all-high      (every high-stake item)
none          (default; exit cleanly)
draft N       (flip item N to category=reply, append to replies file)
skip N        (drop item N from the change-order)
```

No item executes without an explicit selection. `/cure` always waits for
the user to pick ids; the orchestrator does not run on the user's behalf
and does not chain from `/age`.

## Phase 3 — Apply

Each approved item dispatches on its routing type through the apply
router (see `references/apply-router.md`). For `/age` sidecars, routing
is by **sidecar of origin**, not by the `category` field value: all
`fixes.json` items route as `edit`; all `suggestions.json` items route
as `suggestion`. The `category` sub-type (e.g. `deslop.swallowed_catch`)
is informational only. Additional routing types (`ci_fix`, `merge_fix`,
`design`, `reply`) are introduced by `/affine`'s extended schema.

| routing type | handler |
|---|---|
| `edit` (with anchor) | `/cleanup <slug>` (single-item synthesized sidecar) |
| `edit` (no anchor) | direct `cheez-write` (anchor inferred from rationale) |
| `suggestion` | spawn one cook sub-agent per item with `agent_brief_for_cook` |
| `ci_fix` | direct `cheez-write` informed by `log_excerpt` |
| `merge_fix` | `/merge-resolve <file>` |
| `design` | stub spec at `.cheese/specs/<slug>-followup.md`, then `/cook <spec-path>` |
| `reply` | append draft to `.cheese/cure/<slug>.replies.md` — never posts |

Cross-slice calls go through public skill entries only (`/cleanup`,
`/age`, `/cook`, `/merge-resolve`). No reaching into sibling
internals.

For each non-`reply` item, record `touched_paths += item.file`. Replies
do not contribute to the next re-age pass.

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

## Replies file

```
.cheese/cure/<slug>.replies.md

  ## #<thread_id> — <reviewer> on <file>:<line>
  > [original comment]
  Draft reply:
  <body>
```

`reply` items are appended verbatim. The file is the deliverable; the
user reads, edits, and posts manually (the dotfiles `/respond` post-only
mode is a common follow-up). `/cure` never speaks to GitHub.

## Rules

- Default selection is empty. The user gate is the only path to apply.
- `/cure` is invoked manually after `/age` (or `/affine`) prints the
  hand-off; the orchestrator never chains it on the user's behalf.
- Source resolution: explicit `--from age` / `--from affine` overrides
  auto-detect; auto-detect tries age first, then affine.
- Cross-slice calls go through `/cleanup`, `/cook`, `/age`, and
  `/merge-resolve` only — no reaching into sibling internals.
- Re-age cap is 3 turns per invocation. After 3, hand off remaining
  items to the next invocation.
- Replies never post to GitHub. `reply` items are drafted to
  `.cheese/cure/<slug>.replies.md` and excluded from `touched_paths`.

## References

- `references/sources.md` — auto-detect order, `--from` override, the
  missing-sidecar error contract.
- `references/apply-router.md` — category → handler mapping, including
  the `suggestion` → cook sub-agent path.
- `references/re-age.md` — verify loop, diff semantics, 3-turn cap, turn
  log file.
