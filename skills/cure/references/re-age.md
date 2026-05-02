# Re-age — verify loop, diff semantics, 3-turn cap

After the apply phase touches files, `/cure` runs `/age` again, scoped
to the touched paths, to verify the fixes did not introduce new
findings. The result becomes the next iteration of the loop. The loop
has a hard 3-turn cap per invocation.

## Invocation

```
/age --scope <touched_paths>
```

`touched_paths` is the deduplicated union of every non-`reply` item's
`item.file` from the prior apply phase. `reply` items do not contribute
to `touched_paths` — they were drafted to a file, not committed to
disk, so re-aging would find nothing useful and would waste tokens.

The scoped `/age` writes the same sidecars `/age` always writes:
`.cheese/age/<slug>.fixes.json` and `.cheese/age/<slug>.suggestions.json`.

## Diff semantics

After the scoped `/age` returns, `/cure` takes the diff between the new
sidecars and the prior items, and emits **only new or changed** items
as the next iteration:

- An item with a new `id` is **new** → include.
- An item whose `id` matched a prior item but whose `anchor`,
  `rationale`, or `content` changed is **changed** → include.
- An item that exactly matches a prior item is **unchanged** → drop.

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
  "touched_paths": ["src/foo.ts", "src/bar.ts"],
  "reage_new_or_changed": 2
}
```

Each turn appends a row; the file is the basis for tuning the cap.
`reply` items count toward `drafted_replies` and are excluded from
`touched_paths` and from the re-age input.

## Reply exclusion

Replies are drafted to `.cheese/cure/<slug>.replies.md` and never touch
production source. They do **not** add to `touched_paths` and therefore
do not trigger a re-age pass. The user reads, edits, and posts the
replies file manually after the loop exits.
