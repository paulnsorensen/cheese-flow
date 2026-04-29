---
name: test-driven-development
description: >
  Test-first development protocol for turning approved specs into implementation:
  write one failing behavioral test, make it pass with minimal code, refactor only
  while green, and complete explicit self-evaluation before reporting done.
license: MIT
compatibility: Works in markdown-based coding harnesses with an existing test runner.
allowed-tools:
  - bash
metadata:
  owner: cheese-flow
  category: quality
  attribution: Adapted from obra/superpowers test-driven-development skill
---

# test-driven-development

Adapted from the Superpowers `test-driven-development` skill:
https://github.com/obra/superpowers/tree/main/skills/test-driven-development

This is a copied and modified local skill, not a runtime dependency.

## Core rule

**No production code without a failing test first.**

If implementation exists before the test that specifies it, discard that
implementation and restart from the test. The point is not coverage; the point
is proving the test can catch the missing behavior.

## When to use

Use this skill for:

- New behavior from an approved spec.
- Bug fixes.
- Refactors that change externally visible behavior.
- Test hardening after weak assertions are found.

Ask the user before skipping test-first work for generated code, throwaway
experiments, or configuration-only changes.

## Red → Green → Refactor loop

### 1. Red: write one failing test

Write the smallest test that captures one expected behavior from the spec.

The test must:

- Name the behavior clearly.
- Exercise the public surface, not private implementation details.
- Use real code unless an external boundary makes a fake unavoidable.
- Assert exact values, specific errors, or concrete state changes.

### 2. Verify red

Run the narrowest relevant test command.

Confirm:

- The test fails.
- The failure is expected.
- The failure is caused by missing behavior, not a typo, bad import, or broken
  test setup.

If the test passes immediately, the test is not proving the new behavior. Fix
the test before writing implementation.

### 3. Green: write minimal implementation

Implement only enough to satisfy the failing test.

Do not add speculative options, helper frameworks, future extension points, or
extra features that the current test does not require.

### 4. Verify green

Run the narrow test again and confirm it passes. Then run the appropriate wider
quality gate for the changed area.

If production code fails the test, change production code. Do not weaken the
test unless the spec was wrong and the user approves the correction.

### 5. Refactor while green

Clean names, remove duplication, and simplify structure only after the tests
pass. Keep the behavior unchanged and re-run the relevant test after cleanup.

## Assertion strength checklist

Before accepting a test, check:

- [ ] It would fail if the returned value were wrong.
- [ ] It checks collection contents, not only collection length.
- [ ] It checks the specific error type/message for failure paths.
- [ ] It avoids no-crash-only success assertions.
- [ ] It verifies mock or fake call arguments when calls matter.
- [ ] It tests the system under test, not the fake itself.
- [ ] It avoids tautologies and broad truthiness checks.

## Self-evaluation checklist

Complete this before reporting done:

- [ ] Every new behavior has at least one test.
- [ ] Each new test was observed failing before implementation.
- [ ] Each red failure matched the intended missing behavior.
- [ ] Implementation stayed within the approved spec.
- [ ] Refactors happened only after green.
- [ ] Relevant tests and quality gates pass.
- [ ] No weak assertions remain in changed tests.
- [ ] Any skipped TDD step is explicitly reported with the reason.

## Stop signals

Stop and correct course if any of these happen:

- Code was written before a failing test.
- A test passes immediately for new behavior.
- The failure reason cannot be explained.
- The implementation grows beyond the current spec.
- Assertions only check existence, truthiness, or no-crash success.
- You are tempted to say "I'll add tests after."

## Final report

Include a compact TDD summary:

- Red tests written and observed failure reason.
- Green implementation summary.
- Refactor summary, if any.
- Quality gates run.
- Completed self-evaluation checklist.
