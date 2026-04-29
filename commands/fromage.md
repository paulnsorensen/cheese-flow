---
name: fromage
description: Spec-First flow entry point. Routes a known, fully-specified feature through Cut (TDD red tests) → Cook (implement) → Press (adversarial post-impl) → Age (review). Culture is intentionally minimal — the spec is the source of truth, not a fresh codebase scan.
argument-hint: "<spec path | <harness>/specs/<slug>.md | inline spec body>"
---

# /fromage

`/fromage` is the entry point for the **Spec-First Flow** (Flow 1 of the
seven canonical cheese-flow flows). Use it when a complete spec already
exists (typically authored via `/mold`) and you want the agent to execute
it end-to-end as a single coherent feature.

This is the directed-execution mode. The architectural thinking is done.
The agent's job is reliable delivery along a predetermined path. If the
spec is wrong, the code will be wrong — there is no in-flow loop back to
discovery.

## Flow

The canonical Spec-First flow in the design doc is `Cook → Cut → Press →
Age`, where the stage names refer to *pipeline phases* (plan → decompose
→ execute → review). The cheese-flow agent ecosystem has assigned
TDD-flavored roles to those names:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Plan / decompose | Orchestrator (no sub-agent spawn) | Read spec, validate gates, derive task list |
| Define contract | `cut` sub-agent | Write failing tests pinning the spec's named obligations |
| Execute | `cook` sub-agent | Production code that turns Cut's red tests green |
| Adversarial verify | `press` sub-agent | Post-impl boundary / chaos / integration tests |
| Review | `age` skill | Six-dimension merged review |

So the **actual sub-agent dispatch order is `Cut → Cook → Press → Age`**
(TDD discipline: contract before implementation). Culture is folded into
the orchestrator's spec read — no full-repo scan, no architectural
exploration. The spec already encodes the architectural decision.

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Discover the approach (no spec yet) | `/explore` |
| Write a spec and stop | `/mold` |
| Walk an N-task backlog one at a time | `/incremental` |
| Decompose a large spec into parallel worktree atoms | `/fromagerie` |
| Continue a partially-done PR | `/pr-finish` |
| Fix a bug | `/debug` |
| Just review existing code | `/age` |

`/fromage` is for **one coherent feature, sequential execution, single
Age gate at the end**. If the spec contains many independent atoms that
can run in parallel, redirect to `/fromagerie`. If the spec contains a
linear backlog of small per-task changes that each deserve their own Age
gate, redirect to `/incremental`.

## Why Culture is minimal here

The Quintessential flow doc characterises Spec-First Culture as "light —
the agent only needs to scan relevant files for patterns, not explore the
entire codebase." A full Culture pass on a known spec is wasted tokens:
the spec already encodes the architectural decision. The orchestrator's
inline pre-pass is scoped to:

- The spec body itself (Problem, Goals, Non-goals, Approach, Risks,
  Quality gates, Open questions).
- The files named in the spec's Approach section, sampled via
  `cheez-read` outline mode and `cheez-search` for symbol verification.

If the orchestrator cannot ground the plan against the spec — for example
because the spec's Approach is too vague to act on — halt and redirect to
`/mold` or `/explore`. Do not silently expand into a Culture stage; that
is a different flow.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Plan derivation (orchestrator) | Read spec + light grounding | `cheez-search`, `cheez-read` outline mode on spec-named files; `Write` to `$TMPDIR/fromage-<slug>-plan.md` | Production-file edits; full-repo scans; renegotiating the spec; adding goals not in the spec; dropping non-goals |
| Cut | TDD red-tests | Write failing tests under `tests/` pinning each named obligation in the spec; run the test command to confirm red | Production-file edits; inventing edge cases the spec did not name (that's Press); commits |
| Cook | Implement | `cheez-write` on production files to turn Cut's red tests green; read-only Bash for build/test verification | Test-file edits (Cut owns red, Press owns post-impl); build-config silencing; mutating git |
| Press | Adversarial post-impl | Boundary / chaos / integration test additions under `tests/`; run the test command and capture failures only | Production-file edits; build-config silencing; mutating git |
| Age | Review | The standard `age` skill six-dimension review, scoped to the spec's net diff and verified against the spec's Quality gates | Re-opening the design conversation; widening scope beyond the spec |

## Execution protocol

The orchestrator runs the stages sequentially. Each stage hands off via
its structured-summary contract (defined on `agents/<stage>.md.eta`).
The orchestrator works from summaries; downstream stages read the prior
stage's full report from `$TMPDIR` only when they need deeper context.

Pick a kebab-case `<slug>` from the spec's title at step 1 and reuse it
across every $TMPDIR path for the run.

### Step 1 — resolve, validate, classify, confirm

1. **Resolve `$ARGUMENTS`** to a concrete spec. Accept
   `<harness>/specs/<slug>.md`, an absolute path to a markdown file with
   the `/mold` skeleton, or an inline spec body. If the input is a rough
   idea or incomplete spec, redirect to `/mold` and stop.
2. **Validate the spec.** It must contain at minimum the Approach and
   Quality gates sections. If either is missing, halt and recommend
   `/mold` to complete the spec before execution. Do not proceed on a
   half-specified plan — that is the failure mode this flow is designed
   to avoid.
3. **Classify the shape.** If the Approach section enumerates many
   independent units of work (typically >= 4 non-overlapping atoms),
   recommend `/fromagerie` and ask for confirmation before continuing in
   single-feature mode. If it enumerates a linear per-task backlog,
   recommend `/incremental`.
4. **Derive a kebab-case `<slug>`** from the spec's title (e.g.
   `add-redis-rate-limiter`). Reuse it for every $TMPDIR path below.
5. **Derive the plan.** Write a one-screen plan to
   `$TMPDIR/fromage-<slug>-plan.md` enumerating, for each Approach item:
   the public symbol(s) Cut must pin down, the production files Cook is
   allowed to touch, and the Quality-gate command Age will run.
6. **Announce** the planned path — `Cut → Cook → Press → Age` (sub-agent
   dispatch order; pipeline-phase label in the spec doc is `Cook → Cut →
   Press → Age` — see "Flow" above) — the slug, and the spec's Quality
   gates (the exact commands Age will verify).
7. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow scope, or supply extra context. Until
   confirm, no sub-agent runs.

### Step 2 — Cut (TDD contract definition)

Spawn the `cut` sub-agent against the plan to write red tests pinning
each named obligation in the spec. Cut is forbidden from writing to
production files (its source frontmatter disallows `Edit`/`NotebookEdit`;
its Permission Contract names tests-only writes).

```
Agent(
  subagent_type="cut",
  description="Write red tests for <spec title>",
  prompt="Spec-First Flow (Flow 1) Cut step for slug=<slug>.\n\n
Read the plan first: $TMPDIR/fromage-<slug>-plan.md.\n
Read the spec: <spec path or inline body>.\n\n
Deliverable: write the full Cut Report to $TMPDIR/fromage-cut-<slug>.md and return the structured Cut Summary (max 1500 chars, per agents/cut.md.eta).\n\n
Hard constraints:\n
- Pin only the obligations the spec *names* (Approach + Quality gates). Do not invent edge cases — that is Press's job at step 4.\n
- One test per named happy path, one per named error contract, one per named boundary. Names follow `subject_scenario_expectedBehavior`.\n
- Run the project's test command. Confirm every new test is **red** (fails on first run). If any pass without an implementation, the test is wrong — fix it before reporting.\n
- Per your Permission Contract you do not modify production code — that is Cook's job at step 3."
)
```

If Cut returns `partial` or defers a plan unit, surface the deferral and
pause for user direction before continuing — running Cook against an
incomplete contract risks shipping a feature whose contract is not
pinned.

### Step 3 — Cook (implement against red tests)

Spawn the `cook` sub-agent to turn Cut's red tests green. Cook reads
both the plan and Cut's report so it knows the contract surface.

```
Agent(
  subagent_type="cook",
  description="Implement <spec title> against Cut's red tests",
  prompt="Spec-First Flow (Flow 1) Cook step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/fromage-<slug>-plan.md (plan + allowed-touch file list)\n
- $TMPDIR/fromage-cut-<slug>.md (Cut's red test inventory)\n\n
Implement the plan steps with cheez-write. Watch Cut's red tests turn green; capture only failures from the project's build/lint/test command.\n\n
Hard constraints:\n
- Edit only files the plan explicitly names. No 'while we're here' refactors.\n
- Per your Permission Contract you do not modify test files — that is Cut's pre-impl job and Press's post-impl job.\n
- No new features beyond the spec; no goals added; no non-goals dropped.\n
- Write your full Cook Report to $TMPDIR/fromage-cook-<slug>.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

If Cook returns `partial` or `skipped` for a relevant plan step, surface
the blocker and pause for user direction before continuing.

### Step 4 — Press (adversarial post-implementation testing)

Spawn the `press` sub-agent to attack the implementation with the edge
cases the spec did not name — boundary / chaos / integration failure
modes — scored 0–100.

```
Agent(
  subagent_type="press",
  description="Adversarial post-impl tests for <spec title>",
  prompt="Spec-First Flow (Flow 1) Press step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/fromage-<slug>-plan.md (plan + production surface)\n
- $TMPDIR/fromage-cut-<slug>.md (contract pinned by Cut)\n
- $TMPDIR/fromage-cook-<slug>.md (what Cook changed)\n\n
Apply the testing priority order from your charter — invalid inputs, edge cases, integration paths, then happy path. Score every failure 0–100; surface findings >= 50 as critical.\n\n
Per your Permission Contract you do not modify production code. If a failure suggests Cook's implementation is incomplete, surface it as a finding (>= 50) and let the orchestrator route the next iteration.\n\n
Write your full Press Report to $TMPDIR/fromage-press-<slug>.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

### Step 5 — Age (review, no-fix mode)

Invoke the `age` skill in `--no-fix` mode so the Fromage orchestrator
stays in control of the fix loop. `/age` would otherwise prompt for its
own Press cycle and double-spawn it.

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-plus-tests-touched-by-cut-and-press>"
)
```

The age skill writes its merged Age Report to `$TMPDIR/age-<slug>.md`
and returns a structured summary listing findings >= 50, verified
against the spec's Quality gates.

### Step 6 — fix loop, spec-invalidation halt, or success

Inspect the Age summary returned at step 5 plus the Press findings from
step 4.

- **No findings >= 50, Press is green, and the spec's Quality gates
  pass** → success. Surface the cumulative summary (Cut's contract count
  + Cook's diff stat + Press's robustness assessment + Age's "clean")
  and stop.
- **One or more findings >= 50 against the implementation only** → use
  `AskUserQuestion` to ask the user whether to continue the fix loop. On
  confirm, repeat **Step 3 (Cook)** scoped to the cited files only, then
  **Step 4 (Press)** and **Step 5 (Age)**. Re-running Cut for a fix-loop
  is wasteful — the contract was already pinned at step 2.
- **One or more findings >= 50 that challenge the spec itself** (Age
  finds the spec is internally inconsistent, the Approach contradicts a
  Quality gate, or a non-goal collides with a Quality gate) → halt the
  flow and recommend `/mold` to revise the spec. The locked-spec
  assumption of this flow is broken; continuing would compound the
  error.
- **Loop counter** — track loop count starting at 1. After the **third**
  full Cook → Press → Age loop without convergence, halt and return
  cumulative findings. Further work needs human direction or a fresh
  `/mold` to revise the spec.

## Stop conditions

`/fromage` stops when **any** of the following is true:

- Age returns no findings >= 50, Press is green, and the spec's Quality
  gates pass → success. Surface the cumulative summary and the net diff.
- The spec is missing required sections (Approach or Quality gates) →
  halt and recommend `/mold`. No sub-agent spawns.
- The orchestrator cannot ground the plan against the spec-named files
  (spec is too vague or names files that do not exist) → halt and
  recommend `/mold` or `/explore`. Do not silently expand into a Culture
  stage.
- Cut cannot pin a plan unit (the spec's Approach names a behavior whose
  contract cannot be expressed as a test) → halt; this is a spec defect
  and the user is asked whether to re-enter `/mold` or proceed without
  pinning that unit.
- A Cook → Press → Age fix attempt cycles more than **three** times
  without converging → halt and return cumulative findings. Further
  work needs human direction or a fresh `/mold` to revise the spec.
- Age findings call the spec itself into question (not just the
  implementation) → halt; the spec is invalidated and the user is asked
  whether to re-enter `/mold` or abort.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR`. The exact paths the agents use:

| Artifact | Full report path |
|---|---|
| Plan (orchestrator) | `$TMPDIR/fromage-<slug>-plan.md` |
| Cut | `$TMPDIR/fromage-cut-<slug>.md` |
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
  $TMPDIR seam, plan file, and report formats are unchanged — only the
  spawn mechanism degrades.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strict sequential handoff already matches that constraint.
- **Cursor** has no per-agent allowlist; the read-only invariant on
  Cut and Press (no production edits) is enforced solely by prompt on
  Cursor (each agent's Permission Contract block is the backstop).

In every harness, the four stage agents (`cut`, `cook`, `press`, plus
the `age` skill) ARE the portable surface — the Agent/Skill invocations
are the Claude-flavored binding.

## Deferred behavior

The dispatch protocol above is now wired. Two enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Cut's and Press's
  no-production-write invariants are currently enforced only by each
  agent's Permission Contract prompt and the source-frontmatter
  `disallowedTools` list. The compiler does not yet propagate
  `disallowedTools` / `permissionMode` into the rendered harness
  frontmatter, so on Claude Code the invariant is currently prompt-only
  at runtime.
- **Loop counter persistence** — the three-loop cap is enforced by the
  orchestrator tracking loop count in-context. There is no durable
  counter file; if the Fromage session is resumed in a fresh context the
  cap resets. Persisting loop state under
  `$TMPDIR/fromage-<slug>-state.json` would close this gap.

Both gaps lower **Cross-cutting principle: Permission model per stage**
on the scoreboard, not Flow 1 itself.
