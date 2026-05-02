# Re-age — verify loop, diff semantics, 3-turn cap

After the apply phase touches files, `/cure` runs `/age` again, scoped
to the touched paths, to verify the fixes did not introduce new
findings. The result becomes the next iteration of the loop. The loop
has a hard 3-turn cap per invocation.

## Invocation

```
/age --scope <touched_paths>
```

`touched_paths` is the deduplicated union of `item.file` for every
applied item EXCEPT `reply` and `design`. Both are excluded for the
same reason: they did not edit production source in this loop.

- `reply` items draft to `.cheese/cure/<slug>.replies.md` and never
  touch source.
- `design` items hand off to `/cook` out-of-band on a separate branch.
  `/cook` runs its own `/age` pass, so this loop must not re-age
  `item.file` (which `/cook` may not even touch) on `/cook`'s schedule
  (which is unbounded relative to this loop).

The scoped `/age` writes the same sidecars `/age` always writes:
`.cheese/age/<slug>.fixes.json` and `.cheese/age/<slug>.suggestions.json`.

## Diff semantics

After the scoped `/age` returns, `/cure` takes the diff between the new
sidecars and the prior items, and emits **only new or changed** items
as the next iteration:

- An item with a new `id` is **new** → include.
- An item whose `id` matched a prior item but whose key fields changed is
  **changed** → include. Key fields by item type:
  - Fix items: `anchor`, `rationale`, or `content`
  - Suggestion items: `outline_ref`, `narrative`, or `agent_brief_for_cook`
- An item that exactly matches a prior item is **unchanged** → drop.

**Scope limitation**: the re-age is scoped to `touched_paths` only. Any
unapproved items from the prior turn that were on files **not** in
`touched_paths` will not appear in the scoped re-age and are silently
dropped. To continue processing those items, re-run `/cure <slug>` after
the current apply phase completes — the full sidecar will be re-loaded.

If the diff is empty, the loop exits cleanly. The user sees a one-line
summary; no further turns run.

If the diff is non-empty, ask the user whether to continue into the
next turn. The user can stop the loop at any boundary by selecting
`none` at the next user gate.

## 3-turn cap

The loop has a hard cap of **3 turns per invocation** (`turn <= 3`,
where turns are 1-indexed). After turn 3, force-exit even if the diff
is non-empty. Surface the
remaining items as a one-line "next session" hand-off:

```
3-turn cap reached. <N> items remain — run /cure <slug> again to continue.
```

The cap value is a design choice and is **explicitly flagged for
post-implementation review** per the spec. The intent is to bound
oscillation when a fix re-introduces a finding; 3 is enough for a
fix → verify → tweak cycle but small enough that runaway loops cannot
quietly burn budget. Tune the value once we have real session data.

## Turn log

Every turn writes a row to `.cheese/cure/<slug>.turns.log.json` so the
cap can be tuned from real data:

```json
{
  "turn": 1,
  "input_items": 12,
  "approved": 7,
  "applied": 6,
  "skipped": 1,
  "drafted_replies": 2,
  "dispatched_design": 1,
  "touched_paths": ["src/foo.ts", "src/bar.ts"],
  "reage_new_or_changed": 2
}
```

Each turn appends a row; the file is the basis for tuning the cap.
`reply` items count toward `drafted_replies`; `design` items count
toward `dispatched_design`. Both are excluded from `touched_paths` and
from the re-age input.

## Re-age exclusions

Two item types do not contribute to `touched_paths` and therefore do
not trigger a re-age pass:

- **`reply`** — drafted to `.cheese/cure/<slug>.replies.md`, never
  touches source. The user reads, edits, and posts manually after the
  loop exits.
- **`design`** — handed off to `/cook` on a separate branch. `/cook`
  runs its own `/age` pass; this loop has no business re-aging files
  `/cook` may or may not touch on a schedule it does not control.
