---
name: cure
description: Finish what /age started — load both sidecars, render a unified stake table, gate on user approval, apply via /cleanup + cook sub-agents + /merge-resolve, then re-age the touched paths up to a 3-turn cap.
argument-hint: "<slug> [--from age|affine]"
---

# /cure

`/cure` is the single hand-off target after `/age` (and after `/affine` for
the iterate path). In cheesemaking, curing follows aging — the verb fits
the post-`/age` step. Where `/age` reviews and emits sidecars, `/cure`
loads them, gates on the user, applies the items through the right
handler, and re-ages the touched paths.

## Execution

Invoke the `cure` skill with `$ARGUMENTS`. The skill owns sidecar load,
unified stake-table rendering, the user gate, the apply router, and the
re-age verify loop.

Do not reimplement orchestration in this command. This file is the
user-facing contract; `skills/cure/SKILL.md` is the implementation.

## Loop phases

```
load → user gate → apply → re-age → (turn)
```

- **load** — read `.cheese/<source>/<slug>.fixes.json` and the optional
  `<slug>.suggestions.json`, merge into one item list. Source is
  auto-detected (age first, then affine) or pinned with `--from`.
- **user gate** — render the items as a stake-grouped table; nothing
  applies until the user picks ids by hand. The default selection is
  empty.
- **apply** — each approved item routes to the right handler:
  `/cleanup`, direct `cheez-write`, a cook sub-agent, `/merge-resolve`,
  or `/cook` with a stub spec.
- **re-age** — `/age --scope <touched-paths>` runs internally over what
  changed; new findings become the next iteration. Hard cap: 3 turns
  per invocation.

## Arguments

```
/cure <slug>                  # auto-detect: age sidecar first, then affine
/cure <slug> --from age       # pin source: .cheese/age/<slug>.*
/cure <slug> --from affine    # pin source: .cheese/affine/<slug>.*
```

## Companions

| Skill / command | Boundary |
| --- | --- |
| `/age` | Produces the sidecar pair `/cure` consumes, and re-runs scoped to touched paths inside the loop. |
| `/affine` | The iterate-source counterpart. `/affine` collects external feedback (PR, manual) into a sidecar; `/cure` consumes it identically to an `/age` sidecar. |
| `/cleanup` | Mechanical applicator for anchored `edit` items. `/cure` calls it with the original `<slug>` directly. |
| `/cook` | Handles `design` items: `/cure` writes a stub spec at `.cheese/specs/<slug>-followup.md`, `/cook` implements it. |
| `/merge-resolve` | Handles `merge_fix` items, one file at a time. |

## What `/cure` does NOT do

- Run automatically after `/age`. The user types `/cure <slug>` once
  `/age` prints the hand-off; the orchestrator does not chain on the
  user's behalf.
- Apply items without explicit approval. The user gate is mandatory and
  the default selection is empty.
- Send replies to GitHub. `reply` items are drafted to
  `.cheese/cure/<slug>.replies.md` for the user to send manually.
- Ingest external feedback (PR threads, manual bullets, CI failures,
  merge conflicts). That is `/affine`'s job; `/cure` only consumes the
  sidecar shape.

## Output

- `.cheese/cure/<slug>.replies.md` — drafted PR replies for human review.
- `.cheese/cure/<slug>.turns.log.json` — per-turn input/output counts so
  the 3-turn cap can be tuned from real data.
- A run report summarizing applied items, skipped items, drafted
  replies, re-age findings, and any items deferred past the cap.
