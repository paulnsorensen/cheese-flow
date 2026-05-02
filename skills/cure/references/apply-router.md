# Apply router — category to handler

Each approved item is dispatched on `category` to a single handler. The
handler is the only thing that touches production paths. Cross-slice
calls go through public skill entries (`/cleanup`, `/cook`, `/age`,
`/merge-resolve`); internals are not imported.

## Mapping

| category | handler |
|---|---|
| `edit` (with anchor) | `/cleanup <slug>` (single-item synthesized sidecar) |
| `edit` (no anchor) | direct `cheez-write` (anchor inferred from rationale) |
| `suggestion` | spawn one cook sub-agent per item with `agent_brief_for_cook` |
| `ci_fix` | direct `cheez-write` informed by `log_excerpt` |
| `merge_fix` | `/merge-resolve <file>` |
| `design` | synthesize stub spec at `.cheese/specs/<slug>-followup.md`, delegate `/cook <spec-path>` |
| `reply` | append draft to `.cheese/cure/<slug>.replies.md` — NEVER posts to GitHub |

## Per-handler detail

### `edit` (with anchor) → `/cleanup`

Synthesize a minimal sidecar with a single item carrying the v1 required
keys, write it to `.cheese/age/<slug>.fixes.json`, and call
`/cleanup` with the slug. `/cleanup` runs its hash-anchored apply path;
on hash mismatch the cleanup-wolf re-anchors via narrative match. The
result feeds back into the loop's `touched_paths`.

### `edit` (no anchor) → `cheez-write`

`/affine`-sourced items often have no anchor (PR or manual provenance).
Read the file at the location named in the rationale, use `cheez-search`
to locate the target, then apply the edit with `cheez-write`. The
rationale is the anchor proxy; record the resulting file in
`touched_paths`.

### `suggestion` → cook sub-agent

`suggestion` items are judgment-shaped briefs from `/age` — narrative
fixes that need an LLM to interpret and write. For each approved
suggestion, spawn one cook sub-agent with `agent_brief_for_cook` as the
imperative brief, plus `outline_ref` (line range) and `narrative`
(context) for orientation. The sub-agent applies the change with
`cheez-write`. Multiple suggestions targeting the same file are
serialized so the second sub-agent reads the first's result; cross-file
suggestions can run in parallel.

After each sub-agent returns, record `touched_paths += item.file`.

### `ci_fix` → `cheez-write` (informed by `log_excerpt`)

Read `log_excerpt` for the failing line / file / message, locate the
target with `cheez-search`, apply the fix with `cheez-write`. The
`job_id` is recorded in the run report so the user can re-run only the
failed job after the loop.

### `merge_fix` → `/merge-resolve <file>`

For each path in `conflicting_paths`, delegate to `/merge-resolve`. The
merge-resolve skill owns mergiraf, git rerere, and kdiff3; `/cure` does
not reach into its internals. After merge-resolve returns, the file path
is added to `touched_paths`.

### `design` → stub spec + `/cook` (excluded from re-age)

Architectural changes do not belong in the same loop as line-level
fixes. Write a stub spec to `.cheese/specs/<slug>-followup.md` with the
item's rationale as the problem statement, then delegate
`/cook <spec-path>`. `/cook` runs its full red-green-refactor flow on
the new spec, on its own branch, with its own `/age` pass at the end.

`design` items do **not** add to `touched_paths` — same exclusion as
`reply`. Re-aging `item.file` would verify the wrong thing (`/cook`
may not edit it) at the wrong time (`/cook` may not have finished).
Verification is `/cook`'s responsibility, not this loop's.

`/cure` records the dispatch in the turn log under `dispatched_design`
and surfaces it in the loop summary so the user knows a `/cook` task
was kicked off. The original `/cure` invocation continues with the
remaining items.

### `reply` → append to replies file (NEVER posts)

Append a draft entry to `.cheese/cure/<slug>.replies.md`:

```
## #<thread_id> — <reviewer> on <file>:<line>
> [original comment]
Draft reply:
<body>
```

The replies file is the deliverable. `/cure` NEVER posts to GitHub; the
user reads, edits, and sends manually (the dotfiles `/respond` post-only
mode is a common follow-up). Reply items do **not** add to
`touched_paths` and therefore do not trigger a re-age pass.

## Touched paths

Every handler except `reply` records the file it modified into
`touched_paths`. The re-age phase reads this list and runs:

```
/age --scope <touched_paths>
```

The diff between the new sidecar and the prior items becomes the next
iteration. The loop has a 3-turn cap; after the cap, remaining items
hand off to the next `/cure` invocation. See `re-age.md` for the diff
semantics and turn-log file.
