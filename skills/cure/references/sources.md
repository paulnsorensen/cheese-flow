# Sources — sidecar resolution for `/cure`

`/cure` consumes the same v2 additive sidecar shape as `/age` and
`/affine`. The only thing this reference adds is **which directory** the
sidecar lives in and how `/cure` picks it. The schema fields are
documented in the Schema section below.

## Sidecar paths

| Source | Fixes file | Suggestions file (optional) |
|---|---|---|
| `/age` | `.cheese/age/<slug>.fixes.json` | `.cheese/age/<slug>.suggestions.json` |
| `/affine` | `.cheese/affine/<slug>.fixes.json` | `.cheese/affine/<slug>.suggestions.json` |

`/age` always emits both files. `/affine` emits the fixes file; the
companion `suggestions.json` is optional. `/cure` loads whichever is
present and merges into a single item list — a missing
`suggestions.json` is not an error.

## Auto-detect

When the user invokes `/cure <slug>` with no `--from` flag, resolve the
source in this order:

1. **age first** — if `.cheese/age/<slug>.fixes.json` exists, set
   `source = age` and use `.cheese/age/<slug>.*`.
2. **affine fallback** — else if `.cheese/affine/<slug>.fixes.json`
   exists, set `source = affine` and use `.cheese/affine/<slug>.*`.
3. **neither present** — fail with the missing-sidecar error below.

The chosen source is announced in one line before any further work:

```
source: age (.cheese/age/<slug>.fixes.json + .cheese/age/<slug>.suggestions.json)
```

## Explicit `--from` override

```
/cure <slug> --from age       # pin to .cheese/age/<slug>.*
/cure <slug> --from affine    # pin to .cheese/affine/<slug>.*
```

`--from` always overrides auto-detect. If the pinned directory has no
`<slug>.fixes.json`, fail with the missing-sidecar error — `--from`
never silently falls back to the other directory.

## Missing-sidecar error

When neither directory has `<slug>.fixes.json` (auto-detect) or the
pinned directory has none (`--from`), abort with:

```
ERROR: no fixes sidecar found for slug "<slug>".

  tried: .cheese/age/<slug>.fixes.json     (not found)
  tried: .cheese/affine/<slug>.fixes.json  (not found)

Run /age (or /affine) first to generate the sidecar.
```

`/cure` never invents items. If the sidecar is missing, the user runs
the upstream skill and re-tries.

## Schema

Fix items and suggestion items have different schemas:

**Fix items** (from `fixes.json`):

| field | required |
|-------|----------|
| `id`, `dimension`, `file` | yes |
| `anchor` | yes — tilth `line:hash` anchor |
| `content`, `rationale`, `category` | yes |

**Suggestion items** (from `suggestions.json`):

| field | required |
|-------|----------|
| `id`, `dimension`, `file` | yes |
| `outline_ref` | yes — line range, not a hash anchor |
| `narrative`, `agent_brief_for_cook` | yes |

V2 optional fields (`pr_thread_id`, `review_body_id`, `reviewer`,
`job_id`, `log_excerpt`, `conflicting_paths`) are tolerated on either
type. `/cleanup` validates fix-item keys; the apply router enforces the
keys each handler needs.
