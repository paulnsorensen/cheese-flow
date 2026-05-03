# Apply router — routing type to handler

Each approved item dispatches by sidecar of origin to a single handler.
The handler is the only thing that touches production paths. Cross-slice
calls go through public skill entries (`/cleanup`, `/cook`, `/age`);
internals are not imported.

## Mapping

| routing type | handler |
|---|---|
| `edit` | `/cleanup <slug>` (single-item synthesized sidecar) |
| `suggestion` | spawn one cook sub-agent per item with `agent_brief_for_cook` |

`fixes.json` items route as `edit`; `suggestions.json` items route as
`suggestion`. The `category` sub-type on a fix item (e.g.
`deslop.swallowed_catch`) is informational only and does not change
handler dispatch.

## Per-handler detail

### `edit` → `/cleanup`

Synthesize a minimal sidecar with a single item carrying the v1 required
keys (`id`, `dimension`, `file`, `anchor`, `content`, `rationale`,
`category`), write it to `.cheese/age/<slug>.fixes.json`, and call
`/cleanup` with the slug. `/cleanup` runs its hash-anchored apply path;
on hash mismatch the cleanup-wolf re-anchors via narrative match. The
result feeds back into the loop's `touched_paths`.

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

## Touched paths

Every handler records the file it modified into `touched_paths`. The
re-age phase reads this list and runs:

```
/age --scope <touched_paths>
```

The diff between the new sidecar and the prior items becomes the next
iteration. The loop has a 3-turn cap; after the cap, remaining items
hand off to the next `/cure` invocation. See `re-age.md` for the diff
semantics and turn-log file.
