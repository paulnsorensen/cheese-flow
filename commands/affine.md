---
name: affine
description: Collect external feedback (PR threads, CI failures, merge conflicts, manual bullets) and classify it stake-weighted into a /cure-ready v2 sidecar. Collector + classifier only — /cure owns apply, replies, and re-age.
argument-hint: "[--from <pr_url|pr_num>] [--manual]"
---

# /affine

`/affine` is the *affineur* — the cheese ripener who turns wheels and adjusts
conditions during aging. Where `/mold` → `/cook` → `/age` is the forward
path, `/affine` ingests external feedback that `/age` cannot see: PR review
threads, CI failures, merge conflicts, or a hand-typed list. The output is
a `/cure`-ready v2 sidecar.

## Execution

Invoke the `affine` skill with `$ARGUMENTS`. The skill owns source
auto-detect, change-order assembly, stake-weighted classification, sidecar
emission, and the printed hand-off to `/cure`.

Do not reimplement orchestration in this command. This file is the
user-facing contract; `skills/affine/SKILL.md` is the implementation.

## Loop phases

```
collect → classify → emit sidecar → hand off to /cure
```

- **collect** — pull items from the active source: PR review threads
  (with CI failures and merge conflicts folded in when a PR is on the
  branch) or a manual bullet list.
- **classify** — stake-weighted (`high | medium | low`), no numeric
  scores. Build/merge issues land high; pure style cannot.
- **emit sidecar** — write `.cheese/affine/<slug>.fixes.json`. The schema
  is shared with `/age`, so `/cure` can apply both with one router.
- **hand off** — print `Run /cure --from affine <slug>` and exit. The
  user types it; the orchestrator never chains on the user's behalf.

## Arguments

```
/affine                         # auto-detect: PR on branch → manual fallback
/affine --from <pr_url|pr#>     # explicit PR
/affine --manual                # interactive: user types items
```

## Companions

| Skill / command | Boundary |
| --- | --- |
| `/cure` | Consumes the sidecar `/affine` emits. Owns the user gate, apply router, replies file, and re-age verify loop. |
| `/age` | Forward-path review skill. `/affine`'s sidecar schema is shared with `/age` so `/cure` can apply either source. |
| `/move-my-cheese` | Branch rescue without a PR is `/move-my-cheese`'s job, not `/affine`'s. |

## What `/affine` does NOT do

- Apply fixes, draft replies, or speak to GitHub. Apply, replies, and
  posting all live downstream of the sidecar (`/cure` for replies, the
  user for posting).
- Run `/age` itself or maintain a re-age cap. The 3-turn re-age loop
  belongs to `/cure`.
- Consume an existing `/age` sidecar. That path is
  `/cure --from age <slug>`.
- Rescue branches without a PR — that is `/move-my-cheese`.

## Output

- `.cheese/affine/<slug>.fixes.json` — change-order sidecar (v2 schema).
- A printed hand-off line: `Run /cure --from affine <slug>`.
