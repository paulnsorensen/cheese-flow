# Repository rulesets

Source-of-truth for branch protection on this repo. GitHub does **not** auto-apply
files from this directory — apply them with `gh api` or the sync workflow below.

## Files

- `main.json` — protects `main` (default branch). Status: starts in `evaluate` mode for safe rollout.

## Apply

```bash
# Create
gh api repos/paulnsorensen/cheese-flow/rulesets \
  --method POST --input .github/rulesets/main.json

# List (note the id)
gh api repos/paulnsorensen/cheese-flow/rulesets --jq '.[] | {id, name, enforcement}'

# Update an existing ruleset
gh api repos/paulnsorensen/cheese-flow/rulesets/<RULESET_ID> \
  --method PUT --input .github/rulesets/main.json

# Delete
gh api repos/paulnsorensen/cheese-flow/rulesets/<RULESET_ID> --method DELETE
```

## Rollout

1. Apply with `enforcement: "evaluate"` (the default in `main.json`).
2. Open a few PRs; check the **Insights → Rule insights** tab for false positives — especially the `build` status-check context name.
3. Edit `main.json`: change `"evaluate"` → `"active"`. Re-PUT.

## What it protects

| Rule | Effect |
|---|---|
| `deletion` | Can't delete `main` |
| `non_fast_forward` | Can't force-push to `main` |
| `required_linear_history` | Squash-merge only, no merge commits |
| `pull_request` (count=0) | All changes go through a PR; thread resolution required |
| `required_status_checks` | `build` job must pass before merge |
| `bypass_actors` | Repo Admins can bypass via PR (emergency rollbacks) |

## Deliberately omitted

- `required_signatures` — high friction, breaks bot pushes, contradicts force-push protection. Add later if you cut signed releases.
- `required_approving_review_count > 0` — locks out solo maintainer (you can't approve your own PR). Bump to 1 when a second contributor joins.
- `required_deployments` — needs configured Environments; would block all PRs otherwise.

## Notes

- `actor_id: 5` = Admin repository role (built-in).
- `integration_id: 15368` = GitHub Actions (so any check named `build` from Actions counts).
- `~DEFAULT_BRANCH` follows default-branch renames automatically.

See `.cheese/research/github-rulesets-oss-setup.md` for the full rationale, signed-commits how-to, sync-workflow pattern, and trade-offs.
