---
name: cook
description: Sequential spec-to-implementation flow that runs cut, cook, press, and (optionally) assertion-review using Cheez skills as the backbone.
argument-hint: "<approved spec path or well-scoped implementation request>"
---

# /cook

Use `/cook` when the user has a well-thought-out spec or a focused request
ready to implement. The flow is intentionally sequential:

**Spec → cut → cook → press → assertion-review (optional) → package-ready report**

It is not a planning factory. It is not a work splitter. It turns one coherent
spec into tested code through red-green-refactor discipline.

## Companions

| Skill / command | Boundary |
| --- | --- |
| `/mold` | Produces the spec this command consumes. `/cook` never re-asks design questions answered by mold. |
| `/cheese` | Routes here when intent is "implement a known spec". |
| `/age` | Reviews the resulting changes after press finishes. |
| `assertion-review` | Optional drift gate after press; surfaces requirements without strong assertions. |

## Required inputs

Accept one of:

- A spec path (typically `<harness>/specs/<slug>.md` from `/mold`).
- A pasted spec.
- A precise implementation request with acceptance criteria.

If the request is ambiguous, pause and ask for the missing acceptance criteria
before starting cut. Prefer routing the user to `/mold` when the spec is fuzzy.

## Cheez skills backbone

Every phase should use:

- `cheez-search` for code and test discovery.
- `cheez-read` for targeted file understanding.
- `cheez-write` for precise edits.

Do not route the workflow around native read, write, or grep-style habits.
The TDD red → green → refactor protocol is inlined in each subagent prompt;
no separate skill is required.

## Phase 1 — Confirm the contract

Summarize:

- Behavior to build.
- Explicit non-goals.
- Test command or quality gate, if known.
- Files or modules likely in scope, if specified by the user.

Proceed only when the contract is clear enough for a failing test.

## Phase 2 — cut

Invoke the `cut` agent to create failing tests first.

cut must report:

- Test files added or changed.
- The spec requirement each test covers.
- The observed red failure for each new behavior.
- Its self-evaluation checklist.

If tests cannot be made to fail for the expected reason, stop and fix the tests
before cook starts.

## Phase 3 — cook

Invoke the `cook` agent with the spec summary, Cut report, and failing test paths.

cook must:

- Make the cut tests pass with minimal production changes.
- Preserve strong assertions.
- Run narrow tests and relevant wider quality gates.
- Complete its self-evaluation checklist.

If cook reports partial or skipped work, stop and resolve that before press.

## Phase 4 — press

Invoke the `press` agent after cook is green.

press must:

- Check spec coverage.
- Strengthen weak assertions.
- Add focused boundary tests where the implementation is under-tested.
- Score findings and recommend ready, follow-up, or blocked.
- Complete its self-evaluation checklist.

## Phase 5 — assertion-review (optional spec-drift gate)

Invoke `assertion-review` when any of the following hold:

- press flagged uncertain spec coverage.
- The change touches a multi-requirement spec section.
- Reviewers have historically caught drift in the affected slice.

`assertion-review` does not edit code. It produces a coverage matrix mapping
spec requirements to assertions, scores each, and recommends ready / cut
rerun / cook correction / spec amendment.

If assertion-review's recommendation is anything other than "ready for
package", route the work back to the appropriate earlier phase.

## Phase 6 — Package-ready report

Before opening a PR, produce a final self-evaluation:

- [ ] The spec or acceptance criteria are clear.
- [ ] cut wrote failing tests before production changes.
- [ ] cook made the tests pass without speculative behavior.
- [ ] press checked coverage and assertion strength.
- [ ] assertion-review (if invoked) returned "ready for package".
- [ ] Relevant quality gates pass.
- [ ] All changed files are intentional.
- [ ] Remaining risks or skipped checks are documented.

Only proceed to PR creation when the checklist is complete or explicitly waived
by the user.
