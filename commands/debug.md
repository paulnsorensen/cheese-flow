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

## Execution protocol

The orchestrator runs the four stages sequentially. Each stage hands off
via its structured-summary contract (defined on `agents/<stage>.md.eta`).
The orchestrator works from summaries; downstream stages read the prior
stage's full report from `$TMPDIR` only when they need deeper context.

Pick a kebab-case `<slug>` from the failure summary at step 1 and reuse
it across every $TMPDIR path for the run.

### Step 1 — classify and confirm

1. Inspect `$ARGUMENTS`. Confirm it is debug-shaped (failure, error,
   stack trace, regression, failing test). If it is a feature request,
   stop and redirect to `/mold` or `/cheese`.
2. Derive a kebab-case `<slug>` from the failure summary (e.g.
   `null-deref-in-login-handler`).
3. Announce the planned path — `Culture → Cook → Press → Age`, Cut
   skipped, Culture is read-only — and the slug.
4. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow scope, or supply extra reproduction context.

### Step 2 — Culture (read-only diagnosis)

Spawn the `culture` sub-agent in diagnostic mode. Culture is forbidden
from writing to production files (its source frontmatter disallows
`Edit`/`NotebookEdit`; the `Write` carve-out is `$TMPDIR` only).

```
Agent(
  subagent_type="culture",
  description="Diagnose <bug summary>",
  prompt="Debug Flow (Flow 3) Culture pre-pass for slug=<slug>.\n\n
Failure under investigation:\n<verbatim $ARGUMENTS + any extra repro the user supplied at step 1>\n\n
Deliverable: write the full Culture Report to $TMPDIR/fromage-culture-<slug>.md and return the structured Culture Summary (max 2000 chars, per agents/culture.md.eta).\n\n
Required findings before Cook may run:\n
- Suspect files (file:line for each).\n
- Hypothesized root cause with confidence 0-100.\n
- The minimal change surface — *which files Cook is allowed to touch*. Cook MUST NOT widen beyond this list."
)
```

If Culture's confidence < 50 on the root cause, halt the flow. Return
the diagnostic summary to the user; do not proceed to Cook.

### Step 3 — Cook (targeted fix)

Spawn the `cook` sub-agent against Culture's identified files only.

```
Agent(
  subagent_type="cook",
  description="Apply targeted fix for <bug summary>",
  prompt="Debug Flow (Flow 3) Cook step for slug=<slug>.\n\n
Read Culture's full report from $TMPDIR/fromage-culture-<slug>.md before doing anything else. The 'Suspect files' section enumerates the only files you may modify.\n\n
Plan and implement the smallest production change that closes the gap. Cut is skipped because this is a targeted bug fix, not a feature decomposition.\n\n
Hard constraints:\n
- Edit only files Culture explicitly named.\n
- No new features, no refactors, no 'while we're here' cleanups.\n
- Per your Permission Contract you do not modify test files — that is press's job at step 4.\n
- Write your full Cook Report to $TMPDIR/fromage-cook-<slug>.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

If Cook returns `partial` or `skipped` for the relevant plan step,
surface the blocker and pause for user direction before continuing.

### Step 4 — Press (verify + regression test)

Spawn the `press` sub-agent to add a regression test that fails before
the fix and passes after, then run the suite.

```
Agent(
  subagent_type="press",
  description="Verify fix and add regression test for <bug summary>",
  prompt="Debug Flow (Flow 3) Press step for slug=<slug>.\n\n
Read both prior reports first:\n
- $TMPDIR/fromage-culture-<slug>.md (root cause + suspect files)\n
- $TMPDIR/fromage-cook-<slug>.md (what changed)\n\n
Required: write at least one regression test that *would have failed* against the pre-fix code and now passes against Cook's change. Run the project's test command and capture failures only.\n\n
Per your Permission Contract you do not edit production code. If a failure suggests Cook's fix is incomplete, surface it as a finding (>= 50) and let the orchestrator route the next iteration.\n\n
Write your full Press Report to $TMPDIR/fromage-press-<slug>.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

### Step 5 — Age (review, no-fix mode)

Invoke the `age` skill in `--no-fix` mode so the Debug orchestrator
stays in control of the fix loop. `/age` would otherwise prompt for its
own Press cycle and double-spawn it.

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-or-press>"
)
```

The age skill writes its merged Age Report to `$TMPDIR/age-<slug>.md`
and returns a structured summary listing findings >= 50.

### Step 6 — fix loop or success

Inspect the Age summary returned at step 5.

- **No findings >= 50 and Press is green** → success. Surface the
  cumulative summary (Culture's root-cause line + Cook's diff stat +
  Press's regression test name + Age's "clean") and stop.
- **One or more findings >= 50** → use `AskUserQuestion` to ask the
  user whether to continue the fix loop. On confirm, repeat **Step 3
  (Cook)** scoped to the cited files only, then **Step 4 (Press)** and
  **Step 5 (Age)**. Re-running Culture for a fix-loop is wasteful — the
  root cause was already identified at step 2.
- **Loop counter** — track loop count starting at 1. After the **third**
  full Cook → Press → Age loop without convergence, halt and return
  cumulative findings. Further work needs human direction or a fresh
  `/explore` to revisit the approach.

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
`$TMPDIR`. The exact paths the agents use:

| Stage | Full report path |
|---|---|
| Culture | `$TMPDIR/fromage-culture-<slug>.md` |
| Cook | `$TMPDIR/fromage-cook-<slug>.md` |
| Press | `$TMPDIR/fromage-press-<slug>.md` |
| Age (skill) | `$TMPDIR/age-<slug>.md` |

The orchestrator works from the short summaries; downstream stages read
the prior stage's full report from `$TMPDIR` only when they need deeper
context. This keeps the orchestrator's window small across the four
stages even through three Cook → Press → Age fix loops.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)`, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the four stages are then expressed as
  sequential turns with the user supplying each handoff. The slug,
  $TMPDIR seam, and report formats are unchanged — only the spawn
  mechanism degrades.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strict sequential handoff already matches that constraint.
- **Cursor** has no per-agent allowlist; the read-only invariant on
  Culture is enforced solely by prompt on Cursor (the `culture` agent's
  Permission Contract block is the backstop).

In every harness, the four stage agents (`culture`, `cook`, `press`,
plus the `age` skill) ARE the portable surface — the Agent/Skill
invocations are the Claude-flavored binding.

## Deferred behavior

The dispatch protocol above is now wired. Two enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Culture's no-production-write
  invariant is currently enforced only by the agent's Permission
  Contract prompt and the source-frontmatter `disallowedTools` list.
  The compiler does not yet propagate `disallowedTools` /
  `permissionMode` into the rendered harness frontmatter, so on
  Claude Code the invariant is currently prompt-only at runtime.
- **Loop counter persistence** — the three-loop cap is enforced by the
  orchestrator tracking loop count in-context. There is no durable
  counter file; if the Debug session is resumed in a fresh context the
  cap resets. Persisting loop state under `$TMPDIR/fromage-debug-<slug>-state.json`
  would close this gap.

Both gaps lower **Cross-cutting principle: Permission model per stage**
on the scoreboard, not Flow 3 itself.
