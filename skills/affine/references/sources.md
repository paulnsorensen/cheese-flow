# Sources — PR / manual adapters

Every source produces a v2 change-order: a list of `Item`s with the shape
documented in `schema.md`. The PR adapter is the only one that folds in
PR-attribute items (CI failures, merge conflicts) — see D5.

Consuming an existing `/age` sidecar is `/cure --from age <slug>`'s job, not
`/affine`'s (D8). `/affine` only collects *external* feedback — feedback
that `/age` itself cannot see.

## Auto-detect

When the user invokes `/affine` with no flag:

1. If the current branch has an open PR → `source = pr`.
2. Otherwise → `source = manual`.

The chosen source is announced in one line before any further work.

## `from_pr(pr) -> [Item]`

PR adapter. Activates when `source = pr`, whether explicit (`--from`) or
auto-detected. Pulls three streams and merges them into one
change-order.

```
from_pr(pr) -> ChangeOrder(source=pr):
  threads = pr_read("get_review_comments", pr)
              where !is_resolved && !is_outdated
  bodies  = pr_read("get_reviews", pr)
              where body != "" and not dup of any thread
              (link via pull_request_review_id)
  diff    = pr_read("get_diff", pr)

  for thread in threads:
    emit Item(category=edit|reply|design,    # heuristic on suggestion type
              dimension="reviewer",
              file=thread.path, anchor=null,  # PR adapter doesn't anchor
              pr_thread_id=thread.id,
              reviewer=thread.user)

  for body in bodies:
    for bullet in split_into_suggestions(body.body):
      emit Item(... review_body_id=body.id, reviewer=body.user)

  if pr.mergeable_state == "dirty":
    items += merge_items_for(pr)
  if any check has conclusion="failure":
    items += ci_items_for(pr)
```

The PR adapter does not anchor (no `anchor` hash). Items with
`category=edit` and no anchor are emitted as-is; `/cure`'s apply router
infers the location from the rationale at apply time.

### `merge_items_for(pr)` — folded into the PR change-order (D5)

```
merge_items_for(pr) -> [Item]:
  if pr.mergeable_state != "dirty": return []
  for path in unmerged_paths:
    emit Item(category=merge_fix, dimension=merge, stake=high,
              file=path, anchor=null,
              rationale="rebase/conflict block",
              conflicting_paths=[path])
```

There is no `--merge` flag. Merge conflicts are a PR attribute and ride
the same change-order as review feedback.

### `ci_items_for(pr)` — folded into the PR change-order (D5)

```
ci_items_for(pr) -> [Item]:
  failed = gh run list --branch <pr.head> --json + filter conclusion=failure
  for run in failed:
    log = gh run view <id> --log-failed
    for parsed (file, line, msg) in log:
      emit Item(category=ci_fix, dimension=build, stake=high,
                file=file, anchor=null,
                log_excerpt=msg, job_id=run.id)
```

There is no `--ci` flag. CI failures are a PR attribute and ride the
same change-order as review feedback.

## `from_manual() -> ChangeOrder`

Manual adapter. Activates with `--manual` or auto-detect when no PR is on
the branch.

```
from_manual() -> ChangeOrder(source=manual):
  prompt user for free-form bullets (one item per bullet)
  for each bullet:
    emit Item(category=heuristic, dimension="reviewer",
              file=parsed_path_or_null, anchor=null,
              rationale=bullet_text)
```

Manual items have no anchor. The user's bullet text is the rationale; the
classifier uses the bullet to assign a category and dimension.

## Item heuristics

| Bullet shape | category |
|---|---|
| Code change request with a file reference | `edit` |
| Question or discussion only | `reply` |
| Out-of-scope architectural suggestion | `design` |
| "CI failed on X" | `ci_fix` |
| "Merge conflict in Y" | `merge_fix` |

When the heuristic is uncertain, default to `edit`; `/cure`'s user gate
lets the user reclassify (`draft N`) or drop (`skip N`) the item later.
