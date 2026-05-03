---
name: cure
description: Finish what /age started — load both sidecars, render a unified stake table, gate on user approval, apply via /cleanup + cook sub-agents, then re-age the touched paths up to a 3-turn cap.
argument-hint: "<slug>"
---

# /cure

`/cure` is the single hand-off target after `/age`. In cheesemaking,
curing follows aging — the verb fits the post-`/age` step. Where `/age`
reviews and emits sidecars, `/cure` loads them, gates on the user,
applies the items through the right handler, and re-ages the touched
paths.

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

- **load** — read `.cheese/age/<slug>.fixes.json` (required) and the
  optional `.cheese/age/<slug>.suggestions.json`, merge into one item
  list.
- **user gate** — render the items as a stake-grouped table; nothing
  applies until the user picks ids by hand. The default selection is
  empty.
- **apply** — each approved item routes to the right handler:
  `/cleanup` for `edit` items, a cook sub-agent for `suggestion` items.
- **re-age** — `/age --scope <touched-paths>` runs internally over what
  changed; new findings become the next iteration. Hard cap: 3 turns
  per invocation.

## Arguments

```
/cure <slug>
```

## Companions

| Skill / command | Boundary |
| --- | --- |
| `/age` | Produces the sidecar pair `/cure` consumes, and re-runs scoped to touched paths inside the loop. |
| `/cleanup` | Mechanical applicator for anchored `edit` items. `/cure` calls it with the original `<slug>` directly. |
| `/cook` | Hosts the cook sub-agent template that handles `suggestion` items. |

## What `/cure` does NOT do

- Run automatically after `/age`. The user types `/cure <slug>` once
  `/age` prints the hand-off; the orchestrator does not chain on the
  user's behalf.
- Apply items without explicit approval. The user gate is mandatory and
  the default selection is empty.

## Output

- `.cheese/cure/<slug>.turns.log.json` — per-turn input/output counts so
  the 3-turn cap can be tuned from real data.
- A run report summarizing applied items, skipped items, re-age
  findings, and any items deferred past the cap.
