# Schema — v2 change-order sidecar (additive)

The change-order sidecar is the shared shape between `/age`, `/affine`,
and `/cleanup`. v2 is **additive** over v1: every required key from v1
remains required; new fields are optional and tolerated by every
consumer. There is no breaking change.

## File locations

| Source | Path |
|---|---|
| `/age` | `.cheese/age/<slug>.fixes.json` |
| `/affine` | `.cheese/affine/<slug>.fixes.json` |

Both files share this shape:

```json
{
  "version": 2,
  "slug": "<slug>",
  "source": "age | pr | manual",
  "items": [
    {
      "id": "aff-001",
      "category": "edit | reply | ci_fix | merge_fix | design",
      "dimension": "safety | encap | ... | reviewer | build | merge",
      "stake": "high | medium | low",
      "file": "src/foo.ts",
      "anchor": { "start": 42, "end": 58, "hash": "..." },
      "content": "...replacement...",
      "rationale": "...",

      "pr_thread_id": 1234567,
      "review_body_id": 8901234,
      "reviewer": "alice",

      "job_id": "build-x86",
      "log_excerpt": "...",
      "conflicting_paths": ["src/a.ts"]
    }
  ]
}
```

## Required keys (v1, unchanged)

Every item must have all of:

- `id` — stable identifier within the change-order.
- `dimension` — review dimension (`safety`, `encap`, `reviewer`, `build`,
  `merge`, etc.).
- `file` — path the item targets.
- `anchor` — `{ start, end, hash }` for hash-anchored apply, or `null`
  when the source did not anchor (PR adapter, manual, ci_fix, merge_fix).
- `content` — replacement text, or `null` when the handler infers it
  (e.g. `merge_fix`, `reply`).
- `rationale` — narrative explanation; the apply router falls back to
  this when no anchor is present.
- `category` — `edit | reply | ci_fix | merge_fix | design`.

`/cleanup` Phase 1 still aborts when any of these required keys is
missing; no v2 entry relaxes them.

## Optional v2 fields (additive)

These fields carry source-specific provenance and are tolerated by every
consumer. Missing or `null` values are valid.

| Field | Source | Meaning |
|---|---|---|
| `pr_thread_id` | PR | Inline review thread id, used to draft replies. |
| `review_body_id` | PR | Review-body id when the item came from a body bullet. |
| `reviewer` | PR | GitHub login of the reviewer who raised the item. |
| `job_id` | PR (CI) | GitHub Actions run id for `category=ci_fix`. |
| `log_excerpt` | PR (CI) | Failing-build log snippet that informs the fix. |
| `conflicting_paths` | PR (merge) | Paths in conflict for `category=merge_fix`. |

Future siblings of these fields land here without bumping the version.
The schema is intentionally additive: consumers tolerate unknown optional
fields, and `/cleanup` continues to apply v1 sidecars unchanged.

## Compatibility contract

- **`/cleanup`** validates v1 required keys, ignores unknown optional
  fields, and applies hash-anchored items as before. Adding optional
  fields to a sidecar never breaks `/cleanup`.
- **`/age`** emits sidecars whose items omit the PR-only fields
  (`pr_thread_id`, `review_body_id`, `reviewer`, `job_id`,
  `log_excerpt`, `conflicting_paths`). The same file is consumed by
  `/cure --from age <slug>` without conversion.
- **`/affine`** emits sidecars that may include any optional field. The
  sidecar is consumed by `/cure --from affine <slug>`; `/cure`'s apply
  router routes `category=edit` items with anchors to `/cleanup`, which
  ignores the optional fields and applies the v1 contract only.

No breaking change. v2 is unchanged where it matters and additive where
it grows.
