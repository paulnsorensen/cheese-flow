---
name: debug
description: Debug flow entry point. Routes a failure (bug, CI failure, stack trace, regression) through Culture (read-only diagnosis) → Cook (targeted fix) → Press (verify) → Age (review), explicitly skipping Cut.
argument-hint: "<bug description | stack trace | failing test name | CI link | reproduction steps>"
---

# /debug

`/debug` is the entry point for the **Debug Flow** (Flow 3 of the seven
canonical cheese-flow flows). Use it when something is broken and you want
the agent to find the root cause and apply the smallest fix that closes the
gap.

## Flow

```
Culture (read-only trace) → Cook (targeted fix) → Press (verify) → Age (review)
                          └────── Cut is skipped ─────────┘
```

Cut is **deliberately skipped**. A debug fix does not need to be decomposed
into parallel tasks — it is one targeted change. Skipping Cut also prevents
the agent from inventing scope (new tests, refactors, "while we're here"
cleanups) that does not belong in a bug fix.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture | Diagnostic, **read-only** | `cheez-search`, `cheez-read`, `briesearch`, `Bash(git log:*)`, `Bash(git diff:*)`, sandboxed log/repro runs | Any `Edit`, `Write`, `NotebookEdit`, or git-mutating Bash on production files |
| Cook | Targeted fix | `cheez-write` on the files Culture pinpointed; build/test verification via Bash | Edits outside Culture's identified files; new features; refactors unrelated to the root cause |
| Press | Verify | Run the existing test suite + add a regression test that fails before the fix and passes after | Rewriting unrelated tests; chasing flaky tests outside the bug surface |
| Age | Review | The standard `/age` six-dimension review, scoped to the changed files | Re-opening the design conversation; widening scope |

## Dispatch contract

1. **Classify** `$ARGUMENTS` to confirm it is a debug-shaped input
   (failure, error, regression). If the input is actually a feature
   request, redirect to `/mold` or `/cheese` instead of proceeding.
2. **Announce** the planned flow path (`Culture → Cook → Press → Age`,
   Cut skipped) and the read-only invariant on Culture.
3. **Pause** for confirmation. The user may redirect or supply additional
   reproduction context before Culture begins.
4. **Dispatch** the four stages sequentially. Each stage hands off via
   the structured summary contract documented on its agent
   (`agents/<stage>.md.eta`). Culture's report MUST name the suspect
   files and the hypothesized root cause before Cook starts.
5. **Loop on Age failure** — if Age surfaces findings >= 50, loop back to
   Cook (not Culture). Re-running Culture for a fix-loop is wasteful;
   re-running Cook + Press + Age is the evaluator-optimizer cycle.

## Stop conditions

`/debug` stops when **any** of the following is true:

- Age returns no findings >= 50 and Press is green → success.
- Culture cannot identify a root cause with confidence >= 50 → return
  control to the user with the diagnostic summary; do not proceed to Cook.
- A fix attempt cycles through Cook → Press → Age more than **three**
  times without converging → halt and return the cumulative findings.
  Further work needs human direction.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/<stage>-<slug>.md`. The orchestrator works from summaries; the
next stage may read the prior stage's full report if it needs deeper
context. This keeps the orchestrator's window small across the four
stages.

## Deferred behavior

> **Scaffold notice.** Stage dispatch and the Cook→Press→Age fix loop are
> not yet wired. This file documents the contract. The current
> implementation should announce the planned flow, pause for
> confirmation, and stop — it does not yet spawn the stage agents.

The next iteration will:

- Wire the four-stage dispatch via the `Skill` / `Agent` tools.
- Enforce Culture's read-only invariant at the tool layer (no `Edit`,
  `Write`, `NotebookEdit`, or git-mutating Bash) — not just by prompt.
- Implement the three-loop cap on Cook → Press → Age and halt with
  cumulative findings if convergence fails.
