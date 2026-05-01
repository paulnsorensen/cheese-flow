# Repository rulesets

Source-of-truth for branch protection on this repo. GitHub does **not** auto-apply
files from this directory — apply them with `gh api` or the sync workflow below.

## Files

- `main.json` — protects `main` (default branch). Enforcement: `active`.

> Note: `enforcement: "evaluate"` (dry-run mode) is GitHub Enterprise-only.
> On personal/Pro plans the only valid values are `active` and `disabled`.

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

1. Apply (creates the ruleset in `active` mode).
2. Open a small test PR to confirm the `build` status check is recognized and required.
3. If the check name drifts (e.g. CI workflow renamed), edit `main.json` and re-PUT.

If you'd rather stage it first, set `"enforcement": "disabled"` before the initial POST,
then flip to `"active"` and PUT once you've confirmed the rules look right in the UI.

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

This README captures the current rollout guidance and protections; if you want to add deeper rationale, signed-commits how-to, sync-workflow patterns, or trade-off documentation, commit that material somewhere in-repo and reference that committed path here.
