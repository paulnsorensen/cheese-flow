---
name: affine
description: Collect external feedback (PR threads, CI failures, merge conflicts, manual bullets) and classify it stake-weighted into a /cure-ready v2 sidecar. Collector + classifier only — apply, replies, and re-age live in /cure.
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

# Affine — Collect external feedback into a /cure-ready sidecar

`/affine` is the *affineur* — the cheese ripener who turns wheels and adjusts
conditions during aging. Where `/mold` → `/cook` → `/age` builds and reviews
new work, `/affine` ingests *external* feedback that `/age` cannot see: PR
review threads, CI failures, merge conflicts, or a hand-typed list of items.

The loop is intentional and bounded:

```
collect → classify (stake-weighted) → emit sidecar → hand off to /cure
```

`/affine` writes a v2 sidecar and prints the hand-off line. It does not
apply, does not user-gate, does not draft replies, and does not re-age.
Apply, gate, replies, and re-age all belong to `/cure`.

## Arguments

```
/affine                         # auto-detect source
/affine --from <pr_url|pr#>     # explicit PR
/affine --manual                # interactive: user types items
```

### Source auto-detect

When no flag is passed, pick the source in this order:

1. **PR** — if the current branch has an open PR, `source=pr`. Inline review
   threads, review-body bullets, failed CI jobs, and merge conflicts (when
   `mergeable_state == "dirty"`) are all folded into one PR-sourced
   change-order.
2. **manual** — otherwise, fall back to interactive prompt; one item per
   bullet the user types.

Surface the chosen source in one line before any further work. Consuming an
existing `/age` sidecar is `/cure --from age <slug>`'s job, not `/affine`'s.

## Phase 1 — Collect

Adapter detail in `references/sources.md`. The adapters share a single
`Item` shape and emit into a v2 change-order sidecar (see
`references/schema.md`). The schema is **additive** over the v1 contract:
required keys unchanged, new optional fields tolerated.

When `source=pr` and a PR is on the branch, the collector folds three
PR-attribute streams into the same change-order:

- review threads and review-body bullets → `category=edit | reply | design`
- failed CI runs → `category=ci_fix`, `dimension=build`, `stake=high`
- unmerged paths when `mergeable_state == "dirty"` → `category=merge_fix`,
  `dimension=merge`, `stake=high`

There are no `--ci` or `--merge` flags; CI and merge are PR attributes,
not sources.

## Phase 2 — Classify (stake-weighted)

`classify(co) -> ChangeOrder` runs three inputs per item:

- **severity** — fixed by `(category, dimension)`. Bug/security/build/merge
  read high; convention/style reads low.
- **blast** — approximate via `tilth_deps` plus `cheez-search` callers,
  bucketed.
- **consensus** — review state, maintainer status, and dimension overlap.
  `CHANGES_REQUESTED` from a maintainer with multiple dims agreeing
  pushes up; bot-only single-dim pushes down.

Roll up to a bucket: `high | medium | low`. No numeric scores in the
report. Hard rules and the rollup structure live in
`references/classify.md`. Every classification's inputs (severity, blast,
consensus) are logged so the rollup weights can be tuned from real
sessions.

## Phase 3 — Emit sidecar

Write the change-order to `.cheese/affine/<slug>.fixes.json`. The schema is
the v2 additive shape shared with `/age` (see `references/schema.md`).

`/affine` writes the sidecar and exits. Cross-slice work happens via the
sidecar plus the printed hand-off below; nothing else.

## Phase 4 — Hand-off

Print:

```
Affine sidecar: .cheese/affine/<slug>.fixes.json (<N> items)
Next step:      Run /cure --from affine <slug>
```

Do not auto-invoke `/cure`. The user types the hand-off line; the
orchestrator never chains on the user's behalf.

## Rules

- The hand-off is a printed prompt — the user types `/cure` themselves.
  Nothing runs, replies, or publishes without explicit invocation.
- Build/merge always classify high; pure style never classifies high;
  `CHANGES_REQUESTED` without a code reference cannot exceed medium.
- Cross-slice work is the v2 sidecar at `.cheese/affine/<slug>.fixes.json`
  plus the printed hand-off line. No internal imports.
- The v2 schema is additive only; existing consumers continue to apply
  v1 sidecars unchanged.
- `/affine` does not own the user gate, the apply router, the replies
  file, or the re-age verify loop — those belong to `/cure`.

## References

- `references/sources.md` — PR / manual adapters; CI and merge folding.
- `references/schema.md` — v2 additive sidecar schema.
- `references/classify.md` — stake-weighted rollup, inputs, hard rules.
