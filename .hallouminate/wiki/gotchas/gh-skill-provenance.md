# gh skill provenance

A component postcondition must verify **identity**, not a name. For easy-cheese that identity comes from `gh skill list`'s `sourceURL` field, and the field's empty case carries the signal the check depends on.[^1]

## `sourceURL` is derived, and empty means gh did not install it

`gh` derives a skill's `sourceURL` from the `metadata.github-repo` frontmatter in its `SKILL.md`. The field is therefore populated exactly when `gh` installed the skill from a repository, and **empty exactly when it did not** — a locally authored skill dropped into a harness directory by hand has no install metadata and reports `sourceURL: ""`.

That makes the empty string a positive signal rather than missing data. A postcondition that treats empty as "unknown, assume ours" accepts any hand-written file whose name happens to match a core skill. The check compares the normalized `sourceURL` against the expected `owner/repo` and requires a real match, so locally authored look-alikes are rejected.

## Normalize before comparing

`sourceURL` arrives as a URL, and the repository may be registered over HTTPS or SSH. Normalization reduces it to `owner/repo` by stripping a `.git` suffix and trailing slashes, then taking the last two path segments — splitting on `:` as well as `/`, so an SCP-form remote (`git@github.com:owner/repo.git`) reduces correctly instead of never matching.

An SCP-form remote that fails to normalize does not merely skip a check: the postcondition can never converge, so the step reports failed forever and blocks any step depending on it.

## The listing is filtered before identity is checked

Because `gh skill install --all` installs a whole pack, convergence needs the full core quorum from our source, not any single skill. Entries are filtered by scope and by whether the harness appears in `agentHosts` before the `sourceURL` identity test runs, so an unrelated pack reporting its own `sourceURL` cannot veto ours.

## References

[^1]: `python/cheese_flow/adapters/easy_cheese.py` — the `sourceURL` derivation is documented on the postcondition and enforced in its identity comparison; `_normalize_source` performs the reduction. `tests/python/test_adapters.py` covers the locally-authored rejection, the unrelated-pack case, and SCP/HTTPS normalization. Command reference: <https://cli.github.com/manual/gh_skill_install>.
