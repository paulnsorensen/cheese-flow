# Sources — sidecar resolution for `/cure`

`/cure` consumes the sidecar pair emitted by `/age`. This reference
documents where they live, the missing-sidecar error contract, and the
shape of each item type.

## Sidecar paths

| Source | Fixes file (required) | Suggestions file (optional) |
|---|---|---|
| `/age` | `.cheese/age/<slug>.fixes.json` | `.cheese/age/<slug>.suggestions.json` |

`/age` emits both files. The companion `suggestions.json` is optional
— a missing suggestions file is not an error. `/cure` loads whichever
is present and merges the items into a single list.

All harnesses share the project-root `.cheese/` runtime directory.

## Missing-sidecar error

When `.cheese/age/<slug>.fixes.json` does not exist, abort with:

```
ERROR: no fixes sidecar found for slug "<slug>".

  tried: .cheese/age/<slug>.fixes.json     (not found)

Run /age first to generate the sidecar.
```

`/cure` never invents items. If the sidecar is missing, the user runs
`/age` and re-tries.

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

`/cleanup` validates fix-item keys; the apply router enforces the keys
each handler needs.
