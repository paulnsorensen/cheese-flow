# Issue template

Issues are the second artifact type `/mold` can crystallize. They are
GitHub-flavored and stand alone — independent enough to be filed as
`gh issue create --body-file <path>` without the parent spec.

Issues exist when the dialogue surfaced **side-channel actionables**:
out-of-scope follow-ups, bugs spotted along the way, parallel parking-lot
work that happens to belong in the tracker, not the spec — or when a
spec's plan was broken down into independently-grabbable vertical slices.

## Flavors

| Flavor | When | Body shape |
| --- | --- | --- |
| `bug` | dialogue surfaced a defect (Diagnose, or sighted during Ground/Grill) | Reproduction → Expected/Actual → Suggested Fix |
| `slice` | spec's plan broke into thin vertical slices (tracer bullets) | What to build → Acceptance Criteria → Type/Blocked-by |
| `chore` | follow-up cleanup, dependency bump, parking-lot work | Background → Suggested Fix |

A slice issue is a **tracer bullet**: a thin vertical cut through every
layer (schema, API, UI, tests) that delivers a complete, demoable
behaviour change. Many thin slices beat a few thick ones. Each slice is
either `AFK` (can be implemented and merged without human interaction) or
`HITL` (requires human-in-the-loop — a design review, an architectural
decision, a stakeholder sign-off). Prefer AFK over HITL.

## Frontmatter

```yaml
---
kind: issue
flavor: bug | slice | chore
slug: <parent-slug>-<NNN>
title: <Imperative summary, < 70 chars>
created: <YYYY-MM-DD>
status: draft
labels: [<bug|feature|chore|...>, <area-tag>]
priority: <P0|P1|P2|P3>
parent_spec: <slug of the parent spec, if any>
slice_type: AFK | HITL              # slice flavor only
blocked_by: [<sibling issue path>]  # slice flavor only; empty list if none
---
```

`slug` carries a numeric suffix tied to the parent spec's series
(`dark-mode-001`, `dark-mode-002`). Stand-alone issues with no parent use
their own slug (`broken-rate-limit-001`). Slices keep the same series so
`blocked_by` references stay readable.

## Body template — bug flavor

```markdown
# <Imperative title>

## Context
<2-4 sentences. Why this is filed. Reference the parent spec or the
conversation that surfaced it>.

## Reproduction
1. <Step>
2. <Step>
3. <Step>

## Expected Behavior
<What should happen>.

## Actual Behavior
<What happens instead>.

## Suggested Fix
<One paragraph or a fenced pseudocode block, where applicable>.

## Acceptance Criteria
- [ ] <Specific, verifiable criterion — not "works correctly">
- [ ] <Another criterion>

## Out of Scope
<What this issue intentionally does not cover>.
```

## Body template — slice flavor

```markdown
# <Imperative title>

## Parent
<Reference to the parent spec or umbrella issue. Omit for stand-alone
slices>.

## What to build
<End-to-end behaviour change this slice delivers. Layer-agnostic — describe
the behaviour, not the schema/API/UI breakdown>.

## Acceptance Criteria
- [ ] <Specific, verifiable criterion — not "works correctly">
- [ ] <Another criterion>

## Type
<AFK | HITL — and one sentence on why if HITL>.

## Blocked by
- <Reference to the blocking sibling issue>

(Or `None — can start immediately` if no blockers.)

## Out of Scope
<What this slice intentionally does not cover>.
```

## Body template — chore flavor

```markdown
# <Imperative title>

## Context
<2-4 sentences. Why this is filed>.

## Background
<Why now, what triggered the chore. Replaces Reproduction for non-bugs>.

## Suggested Fix
<One paragraph or a fenced pseudocode block, where applicable>.

## Acceptance Criteria
- [ ] <Specific, verifiable criterion>.

## Out of Scope
<What this issue intentionally does not cover>.
```

## Section presence

| Section | bug | slice | chore |
| --- | --- | --- | --- |
| Context | yes | as Parent | yes |
| Reproduction | yes | — | — |
| Expected / Actual | yes | — | — |
| What to build | — | yes | — |
| Background | — | — | yes |
| Type (AFK/HITL) | — | yes | — |
| Blocked by | — | yes | — |
| Suggested Fix | yes | — | yes |
| Acceptance Criteria | yes | yes | yes |
| Out of Scope | when ambiguous | when ambiguous | when ambiguous |

## Filing flow

After the spec write succeeds (or the user picks "Issues only"), `/mold`
offers:

```
Filed:
  - .cheese/specs/<slug>.md       (1 spec)
  - .cheese/issues/<slug>-001.md  (1 issue)
  - .cheese/issues/<slug>-002.md  (1 issue)

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
