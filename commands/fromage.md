---
name: fromage
description: Focused spec-to-implementation TDD flow that runs Cut, Cook, and Press sequentially using Cheez skills as the backbone.
argument-hint: "<approved spec path or well-scoped implementation request>"
---

# /fromage

Use `/fromage` when the user has a well-thought-out spec or a focused request
ready to implement. The flow is intentionally sequential:

**Spec → Cut → Cook → Press → package-ready report**

It is not a planning factory. It is not a work splitter. It turns one coherent
spec into tested code through TDD discipline.

## Required inputs

Accept one of:

- A spec path.
- A pasted spec.
- A precise implementation request with acceptance criteria.

If the request is ambiguous, pause and ask for the missing acceptance criteria
before starting Cut.

## Cheez skills backbone

Every phase should use:

- `cheez-search` for code and test discovery.
- `cheez-read` for targeted file understanding.
- `cheez-write` for precise edits.
- `test-driven-development` for red → green → refactor discipline.

Do not route the workflow around native read, write, or grep-style habits.

## Phase 1 — Confirm the contract

Summarize:

- Behavior to build.
- Explicit non-goals.
- Test command or quality gate, if known.
- Files or modules likely in scope, if specified by the user.

Proceed only when the contract is clear enough for a failing test.

## Phase 2 — Cut

Invoke `fromage-cut` to create failing tests first.

Cut must report:

- Test files added or changed.
- The spec requirement each test covers.
- The observed red failure for each new behavior.
- Its self-evaluation checklist.

If tests cannot be made to fail for the expected reason, stop and fix the tests
before Cook starts.

## Phase 3 — Cook

Invoke `fromage-cook` with the spec summary, Cut report, and failing test paths.

Cook must:

- Make the Cut tests pass with minimal production changes.
- Preserve strong assertions.
- Run narrow tests and relevant wider quality gates.
- Complete its self-evaluation checklist.

If Cook reports partial or skipped work, stop and resolve that before Press.

## Phase 4 — Press

Invoke `fromage-press` after Cook is green.

Press must:

- Check spec coverage.
- Strengthen weak assertions.
- Add focused boundary tests where the implementation is under-tested.
- Score findings and recommend ready, follow-up, or blocked.
- Complete its self-evaluation checklist.

## Phase 5 — Package-ready report

Before opening a PR, produce a final self-evaluation:

- [ ] The spec or acceptance criteria are clear.
- [ ] Cut wrote failing tests before production changes.
- [ ] Cook made the tests pass without speculative behavior.
- [ ] Press checked coverage and assertion strength.
- [ ] Relevant quality gates pass.
- [ ] All changed files are intentional.
- [ ] Attribution for copied or adapted external guidance is preserved.
- [ ] Remaining risks or skipped checks are documented.

Only proceed to PR creation when the checklist is complete or explicitly waived
by the user.
