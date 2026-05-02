# Classify — stake-weighted rollup

`/affine` reports stake as a bucket: `high | medium | low`. There are no
numeric scores in user-facing output. The rollup is intentionally simple
and logged so the weights can be tuned from real sessions.

## Inputs

For each item, classify reads three inputs:

### `severity`

Fixed by `(category, dimension)`. The table:

| dimension | category | severity |
|---|---|---|
| `build` | `ci_fix` | high |
| `merge` | `merge_fix` | high |
| `safety` | `edit` | high |
| `encap` | `edit` | high |
| `spec` | `edit` | high |
| `correctness` | `edit` | high |
| `complexity` | `edit` | medium |
| `deslop` | `edit` | medium |
| `assertions` | `edit` | medium |
| `reviewer` | `edit` | medium |
| `precedent` | `edit` | low |
| `style` | `edit` | low |
| any | `reply` | low |
| any | `design` | medium |

### `blast`

Approximate the change's reach with `tilth_deps` plus `cheez-search`
callers, bucketed:

| call sites | blast |
|---|---|
| > 20 | high |
| 5–20 | medium |
| < 5 | low |
| no anchor (file only) | medium (default) |

Bucketing avoids false precision; the call-graph traversal is bounded.

### `consensus`

Signals about reviewer trust and cross-dim agreement:

- `+` push when:
  - review state is `CHANGES_REQUESTED` from a maintainer
  - 2+ dimensions raise items at the same locus
  - the reviewer is a code owner for the touched path
- `-` push when:
  - the comment is bot-only (Copilot, Coderabbit) and only one dim agrees
  - the reviewer has not approved any prior PR in the slice

`consensus` is bucketed `+ | 0 | -`.

## Rollup

```
stake = roll_up(severity, blast, consensus) ∈ {high, medium, low}
```

Structure: combine `severity` (high/medium/low), `blast` (high/medium/
low), and `consensus` (`+`/`0`/`-`) into a single bucket. `severity` is
the dominant signal; `blast` shifts up at high reach; `consensus` shifts
one bucket either direction.

The exact rollup weight table is `[?]` — pinned during implementation,
documented here in structure now. Every classification's inputs
(`severity`, `blast`, `consensus`) are logged alongside the resulting
`stake` so the table can be backfit from real sessions.

## Hard rules (override the rollup)

These constraints are non-negotiable and override any rollup result:

- **build/merge always high.** Any item with `dimension=build` or
  `dimension=merge` (i.e. `ci_fix` and `merge_fix`) is `stake=high`. The
  rollup never lowers them.
- **pure style never high.** Items with `dimension=style` (or
  conventionally style-only, no behavior change) are at most medium. The
  rollup never raises them.
- **`CHANGES_REQUESTED` without code reference cannot exceed medium.** A
  maintainer may push the consensus signal up, but if the comment carries
  no `path:line` reference and no quoted code, the item is capped at
  `stake=medium` regardless of severity. `CHANGES_REQUESTED` with a code
  reference is uncapped and follows the regular rollup.

## Output table

The user-gate table groups by stake (`high` first, then `medium`, then
`low`), and within each group sorts by file:

```
| id | stake | category | dim | location | summary |
```

`stake` is rendered as the bucket name only — no numbers.

## Logging

For every item, write the inputs and the resulting bucket to the run log
at `.cheese/affine/<slug>.classify.log.json`:

```json
{
  "id": "aff-001",
  "severity": "high",
  "blast": "medium",
  "consensus": "+",
  "stake": "high"
}
```

This log is the basis for tuning the rollup weights.
