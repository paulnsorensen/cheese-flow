# Issue template

Issues are the second artifact type `/mold` can crystallize. They are
GitHub-flavored and stand alone — independent enough to be filed as
`gh issue create --body-file <path>` without the parent spec.

Issues exist when the dialogue surfaced **side-channel actionables**:
out-of-scope follow-ups, bugs spotted along the way, parallel parking-lot
work that happens to belong in the tracker, not the spec.

## Frontmatter

```yaml
---
kind: issue
slug: <parent-slug>-<NNN>
title: <Imperative summary, < 70 chars>
created: <YYYY-MM-DD>
status: draft
labels: [<bug|feature|chore|...>, <area-tag>]
priority: <P0|P1|P2|P3>
parent_spec: <slug of the parent spec, if any>
---
```

`slug` carries a numeric suffix tied to the parent spec's series
(`dark-mode-001`, `dark-mode-002`). Stand-alone issues with no parent use
their own slug (`broken-rate-limit-001`).

## Body template

```markdown
# <Imperative title>

## Context
<2-4 sentences. Why this is filed. Reference the parent spec or the
conversation that surfaced it>.

## Reproduction
1. <Step>
2. <Step>
3. <Step>

(Drop this section for non-bug issues. Replace with `## Background` for
chores or follow-ups).

## Expected Behavior
<What should happen>.

## Actual Behavior
<What happens instead>.

(Drop both for non-bug issues).

## Suggested Fix
<One paragraph or a fenced pseudocode block, where applicable>.

## Acceptance Criteria
- [ ] <Specific, verifiable criterion — not "works correctly">
- [ ] <Another criterion>

## Out of Scope
<What this issue intentionally does not cover>.
```

## Section presence

| Section | Always | Drop when |
| --- | --- | --- |
| Context | yes | — |
| Reproduction | bug only | issue is a follow-up or chore |
| Expected / Actual | bug only | issue is a follow-up or chore |
| Background | non-bug only | issue is a bug |
| Suggested Fix | yes | — |
| Acceptance Criteria | yes | — |
| Out of Scope | when ambiguous | scope is obvious |

## Filing flow

After the spec write succeeds (or the user picks "Issues only"), `/mold`
offers:

```
Filed:
  - <harness>/specs/<slug>.md       (1 spec)
  - <harness>/issues/<slug>-001.md  (1 issue)
  - <harness>/issues/<slug>-002.md  (1 issue)

File these as GitHub issues now? (y/N)
```

If yes, run one `gh issue create --title <frontmatter title> --body-file
<path>` per issue file. Surface the resulting issue URLs back to the user.

## Linkage

- Each issue's `parent_spec` field points at its sibling spec slug.
- The spec's `related` frontmatter array lists the issue file paths.

This bidirectional link is the only structural relationship between the two
artifact types. Everything else is content.

## Collisions

If an issue with the same slug already exists, default to `<slug>-<NNN+1>`
(append next number in series). Never silently overwrite an existing issue
file.
