---
name: incremental
description: Incremental flow entry point. Walks a spec or task list one task at a time through Cook → Cut → Press → Age, looping until the backlog is exhausted or a stop condition fires. Each task's Culture is folded into the orchestrator's per-task plan write — no per-iteration Culture sub-agent.
argument-hint: "<spec path | task-list path | issue ref with checklist>"
---

# /incremental

`/incremental` is the entry point for the **Incremental Build / Spec-Driven
Loop** (Flow 6 of the seven canonical cheese-flow flows). Use it when a
spec, PRD, or checklist already exists and you want the agent to grind
through it one task at a time, with an Age gate after every task.

This is the workhorse flow for day-to-day spec execution. It is **not**
the parallel decomposition pattern — that is `/fromagerie`, which fans
out into worktree-isolated atoms. `/incremental` is sequential: one task,
verified green, then the next.

## Flow

The canonical Incremental flow in the design doc is `[Cook task-N → Cut →
Press → Age] × N`. The cheese-flow agent ecosystem maps those pipeline
phases to TDD-flavored sub-agent roles, identical to `/fromage` per task:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Plan task-N | Orchestrator (no sub-agent) | Extract task from spec, write per-task plan to $TMPDIR |
| Define contract (per task) | `cut` sub-agent | Write failing tests pinning task N's named obligations |
| Execute (per task) | `cook` sub-agent | Production code that turns Cut's red tests green |
| Adversarial verify (per task) | `press` sub-agent | Post-impl boundary / chaos / integration tests |
| Review (per task) | `age` skill | Six-dimension merged review on task N's net diff |

So the **actual sub-agent dispatch order per task** is `Cut → Cook →
Press → Age`. The canonical "Cook task-N" is the orchestrator's planning
step, not a Cook sub-agent dispatch — Cook the agent is a production-code
writer, and dispatching it twice per task (once to plan, once to
implement) would violate its single-purpose Permission Contract.

```
Per task N:
  [orchestrator: write task-N plan] → Cut → Cook → Press → Age
                                                            │
                                                            ▼
                                                       next task
```

```
[plan-1 → Cut → Cook → Press → Age] →
[plan-2 → Cut → Cook → Press → Age] →
[plan-3 → Cut → Cook → Press → Age] → … until backlog exhausted or stop fires
```

Per-task Culture is **not run as a separate sub-agent stage**. The
Quintessential flow specifies per-iteration Culture must be *minimal* —
just enough to ground the agent in patterns relevant to the current
task. That grounding is folded into the orchestrator's per-task plan
write (the orchestrator reads the spec entry, names the files, and pins
the obligations). A full repo scan per task is the exact cost spike this
flow is designed to avoid.

If the spec was authored without a Culture pre-pass and the orchestrator
cannot ground a task at all, halt the loop and recommend `/culture` or
`/mold` on the spec before retrying. Do not silently expand into a
per-task Culture sub-agent dispatch.

## Distinguish from `/fromagerie`

| Aspect | `/incremental` | `/fromagerie` |
|---|---|---|
| Decomposition | Sequential per task | Parallel atoms in worktrees |
| Per-task isolation | Single working tree, in-place | Per-atom worktree branches |
| Gate cadence | Age after every task | Age within each atom + cheese-convoy at the end |
| Best for | Linear backlogs, refactor passes, doc/test sweeps | Independent atoms that can run concurrently |
| Stop cost | One task's worth of work to abort | Many atoms to roll back |

If `$ARGUMENTS` clearly maps to non-overlapping parallel atoms, redirect
to `/fromagerie` before starting the loop.

## Stage contract (per task)

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Plan (orchestrator) | Extract task-N + minimal targeted grounding | `cheez-search`/`cheez-read` scoped to task-named files; `Write` to `$TMPDIR/incremental-<slug>-task-<N>-plan.md` | Full-repo scans; reading unrelated slices; rewriting the spec; merging tasks |
| Cut (per task) | TDD red tests for task-N's named obligations | `cheez-search` / `cheez-read` to validate import paths; `Write` to test files; Bash to run the test command and confirm red | Production-file edits; widening scope beyond task-N; pulling work forward from later tasks; inventing edge cases the task doesn't name |
| Cook (per task) | Implement task-N against Cut's red tests | `cheez-write` on production files named in the per-task plan; read-only Bash for build/test | Test-file edits (Cut owns red, Press owns post-impl); files belonging to later tasks; rebasing or other mutating git |
| Press (per task) | Adversarial post-impl on task-N | Boundary / chaos / integration test additions scoped to task-N; run the test command and capture failures only | Production-file edits; build-config silencing; mutating git |
| Age (per task) | Six-dimension review, **scoped to task N's net diff only** | The standard `age` skill review against the diff Cook + Cut + Press produced for task N | Re-opening the design conversation; widening scope to other tasks; reviewing the whole spec |

## Backlog state

`/incremental` maintains a state file at
`$TMPDIR/incremental-<slug>-state.json` that records, per task:

- Task index, title, source-spec line range.
- Status (`pending`, `in-progress`, `done`, `failed`, `skipped`).
- Age fix-loop attempt count.
- Pointer to the per-task plan file.

The state file is the single source of truth for "where are we in the
backlog". A new `/incremental` invocation on the same spec resumes from
the first non-`done` task (or starts fresh if no state exists).

State file shape (the orchestrator writes/reads this verbatim):

```json
{
  "slug": "<kebab-slug>",
  "spec_path": "<absolute path or harness/specs/<slug>.md>",
  "tasks": [
    {
      "n": 1,
      "title": "<short title>",
      "spec_lines": [12, 28],
      "plan_path": "$TMPDIR/incremental-<slug>-task-1-plan.md",
      "status": "done",
      "fix_loop_attempts": 0
    },
    {
      "n": 2,
      "title": "<short title>",
      "spec_lines": [29, 47],
      "plan_path": "$TMPDIR/incremental-<slug>-task-2-plan.md",
      "status": "pending",
      "fix_loop_attempts": 0
    }
  ]
}
```

## Execution protocol

The orchestrator initializes the backlog at step 1, then walks pending
tasks sequentially at step 2. Each task runs its own four-stage pipeline
(Cut → Cook → Press → Age) with up to a three-loop Cook → Press → Age
fix cap before being marked `failed`. Each stage hands off via its
structured-summary contract (defined on `agents/<stage>.md.eta`). The
orchestrator works from summaries; downstream stages read the prior
stage's full report from `$TMPDIR` only when they need deeper context.

Pick a kebab-case `<slug>` from the spec name at step 1 and reuse it
across every $TMPDIR path for the run.

### Step 1 — resolve, classify, init state

1. Inspect `$ARGUMENTS`. Resolve to a concrete spec or task list:
   - `<harness>/specs/<slug>.md` (canonical),
   - an absolute path to a markdown file with `- [ ]` checkbox tasks,
   - or an issue reference with an embedded checklist.
   - If the spec is unparseable, halt and ask for a structured task list.
2. **Classify** the task list. If tasks look independent and could run in
   worktree-isolated parallel atoms, recommend `/fromagerie` instead and
   pause for confirmation before continuing in sequential mode.
3. **Redirect non-incremental shapes**:
   - bug / stack trace / failing test → `/debug`.
   - fuzzy problem with no clear approach → `/explore`.
   - PR or partial branch → `/pr-finish`.
   - spec missing Approach + Quality gates → `/mold`.
4. Derive a kebab-case `<slug>` from the spec filename or issue title
   (e.g. `auth-refresh-rotation`, `inbox-zero-rewrite`).
5. **Init or resume the state file** at
   `$TMPDIR/incremental-<slug>-state.json`:
   - If absent → enumerate tasks from the spec, populate `tasks[]` with
     `status: "pending"` and `fix_loop_attempts: 0`, write the file.
   - If present → load it; resume from the first task whose status is
     not `done`.
6. **Announce** the planned path (`Cut → Cook → Press → Age` per task,
   looped) and the total task count + resume position.
7. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow the task range (e.g. "tasks 3–5 only"),
   request a fresh state init, or abort.

### Step 2 — per-task pipeline (loop over pending tasks)

For each task `N` whose state is `pending`:

#### Step 2a — orchestrator: write per-task plan

Read the spec slice (`spec_lines`) and write the per-task plan to
`$TMPDIR/incremental-<slug>-task-<N>-plan.md`. The plan must include:

- The task's verbatim spec text.
- Named obligations (function/command surfaces, error contracts,
  boundary requirements) — what Cut will pin.
- Allowed-touch file list — what Cook may edit.
- Quality gates (commands that must pass for Age to clear).

Mark the task `in-progress` in the state file.

#### Step 2b — Cut (per task)

```
Agent(
  subagent_type="cut",
  description="Red tests for task <N>: <task title>",
  prompt="Incremental Flow (Flow 6) Cut step for slug=<slug>, task N=<N>.\n\n
Read the per-task plan first: $TMPDIR/incremental-<slug>-task-<N>-plan.md.\n\n
Deliverable: write the full Cut Report to $TMPDIR/incremental-<slug>-task-<N>-cut.md (override the default fromage-cut-<slug>.md path so per-task artifacts stay isolated) and return the structured Cut Summary (max 1500 chars, per agents/cut.md.eta).\n\n
Hard constraints:\n
- Pin only the obligations the task plan *names* — happy path + named errors + named boundaries. Do not invent edge cases for task <N> — that is Press's job at step 2d. Do not pull work forward from tasks > <N>.\n
- Run the project's test command. Confirm every new test is **red** (fails on first run). If any pass without an implementation, the test is wrong — fix it before reporting.\n
- Per your Permission Contract you do not modify production code — that is Cook's job at step 2c."
)
```

#### Step 2c — Cook (per task)

```
Agent(
  subagent_type="cook",
  description="Implement task <N> against Cut's red tests",
  prompt="Incremental Flow (Flow 6) Cook step for slug=<slug>, task N=<N>.\n\n
Read prior artifacts first:\n
- $TMPDIR/incremental-<slug>-task-<N>-plan.md (allowed-touch file list + Quality gates)\n
- $TMPDIR/incremental-<slug>-task-<N>-cut.md (red test inventory for this task only)\n\n
Implement task <N> with cheez-write. Watch Cut's red tests turn green; capture only failures from the project's build/lint/test command.\n\n
Hard constraints:\n
- Edit only files the task plan explicitly names. No 'while we're here' refactors.\n
- Do NOT touch files reserved for tasks > <N>. The state file enumerates the backlog.\n
- Per your Permission Contract you do not modify test files — that is Cut's pre-impl job and Press's post-impl job.\n
- Write your full Cook Report to $TMPDIR/incremental-<slug>-task-<N>-cook.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

If Cook returns `partial` or `skipped` for the task's plan, surface the
blocker, mark the task `failed` with a one-line reason in the state
file, and pause for user direction before advancing the loop.

#### Step 2d — Press (per task)

```
Agent(
  subagent_type="press",
  description="Adversarial post-impl tests for task <N>",
  prompt="Incremental Flow (Flow 6) Press step for slug=<slug>, task N=<N>.\n\n
Read prior artifacts first:\n
- $TMPDIR/incremental-<slug>-task-<N>-plan.md (named obligations + production surface)\n
- $TMPDIR/incremental-<slug>-task-<N>-cut.md (contract pinned by Cut)\n
- $TMPDIR/incremental-<slug>-task-<N>-cook.md (what Cook changed for task <N>)\n\n
Apply the testing priority order from your charter — invalid inputs, edge cases, integration paths, then happy path. Score every failure 0–100; surface findings >= 50 as critical. Scope your attack surface to task <N>'s production diff only — do not chase regressions in tasks already marked `done`.\n\n
Per your Permission Contract you do not modify production code. If a failure suggests Cook's implementation is incomplete, surface it as a finding (>= 50) and let the orchestrator route the next iteration.\n\n
Write your full Press Report to $TMPDIR/incremental-<slug>-task-<N>-press.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

#### Step 2e — Age (per task, no-fix mode)

Invoke the `age` skill in `--no-fix` mode so the Incremental orchestrator
stays in control of the per-task fix loop.

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-plus-tests-touched-by-cut-and-press-for-task-N>"
)
```

The age skill writes its merged Age Report to
`$TMPDIR/incremental-<slug>-task-<N>-age.md` (override the default
`age-<slug>.md` path so per-task artifacts stay isolated) and returns a
structured summary listing findings >= 50.

#### Step 2f — per-task fix loop (Cook → Press → Age)

Inspect the Age summary plus Press findings.

- **No findings >= 50 and Press is green** → mark the task `done` in the
  state file, surface a one-line cross-task break ("task N/M done, M-N
  remaining"), advance to the next pending task at step 2a.
- **Findings >= 50 against the implementation only** → increment
  `fix_loop_attempts` in the state file. If `< 3`, repeat **Step 2c
  (Cook)** scoped to the cited files only, then **Step 2d (Press)** and
  **Step 2e (Age)**. Re-running Cut for a fix-loop is wasteful — the
  contract was already pinned at step 2b.
- **Findings >= 50 that challenge the task plan itself** (Age finds the
  plan is internally inconsistent, Press uncovers an obligation the plan
  missed, or a Quality gate collides with the task as scoped) → mark the
  task `failed` in the state file, halt the loop, surface cumulative
  findings, and recommend `/mold` on the spec (the spec is wrong, not
  the implementation).
- **`fix_loop_attempts` reaches 3** without convergence → mark the task
  `failed` in the state file, halt the loop, return cumulative findings.
  Further work needs human direction.

#### Step 2g — cross-task hand-off

Between tasks N and N+1:

1. Press for task N must be green (build + tests pass) — enforced at
   step 2f.
2. Age for task N must return no findings >= 50 — enforced at step 2f.
3. State file marks task N `done`.
4. Step 2a for task N+1 starts fresh — it does NOT inherit the per-task
   plan from task N. Each task plans against its own slice of the spec
   to prevent context bleed.

This is the discipline that keeps the flow's per-task cost roughly
constant instead of growing with N.

### Step 3 — backlog complete

When every task in the state file has status `done` (or the user has
ranged the loop with "tasks 3–5 only" and the requested range is
complete):

- Surface the cumulative summary: tasks done / failed / skipped, total
  Cook diff stat across all tasks, Press robustness summary across all
  tasks, Age "clean across N tasks".
- The state file is the durable record of the run; subsequent
  `/incremental` invocations on the same spec see all tasks `done` and
  exit immediately with the cumulative summary.

If any task is `failed` when the loop halts, surface its cumulative
findings and the resume hint: "next pending task is N+1; failed task
N's findings live at `$TMPDIR/incremental-<slug>-task-<N>-age.md`".

## Stop conditions

`/incremental` stops when **any** of the following is true:

- Every task is `done` (or the requested task range is complete) →
  return the cumulative summary.
- A task fails the three-loop Cook → Press → Age cap → halt with
  cumulative findings for that task; state file marks it `failed`.
  Resume after human direction.
- A task's plan itself is invalidated by Age or Press findings → halt;
  recommend `/mold` to revise the spec slice for that task.
- Age cannot be run on a task because Press is not green → halt; do not
  silently advance to the next task.
- The user interrupts between tasks → exit cleanly; the state file
  reflects the next pending task for the next invocation.
- A task requires Culture-level discovery (the orchestrator cannot
  ground without a full repo scan) → halt and recommend `/culture` or
  `/explore` on the spec slice; do not silently expand into a per-task
  Culture sub-agent dispatch.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR`. The exact paths the orchestrator uses (per-task `<N>`):

| Artifact | Full report path |
|---|---|
| State file (durable) | `$TMPDIR/incremental-<slug>-state.json` |
| Per-task plan | `$TMPDIR/incremental-<slug>-task-<N>-plan.md` |
| Cut (per task) | `$TMPDIR/incremental-<slug>-task-<N>-cut.md` |
| Cook (per task) | `$TMPDIR/incremental-<slug>-task-<N>-cook.md` |
| Press (per task) | `$TMPDIR/incremental-<slug>-task-<N>-press.md` |
| Age (per task) | `$TMPDIR/incremental-<slug>-task-<N>-age.md` |

The orchestrator overrides the default `fromage-*-<slug>.md` and
`age-<slug>.md` paths during the loop (per-task reports live in the
`incremental-<slug>-task-<N>-*` namespace) to keep per-task artifacts
isolated and resume-friendly. A stale state file plus its
per-task report folder is the only state the orchestrator must read to
continue after a context loss — the next pending task is the first
`status != done` entry.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)`, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the per-task pipeline is then expressed
  as sequential turns with the user supplying each handoff. The slug,
  per-task $TMPDIR paths, and report formats are unchanged — only the
  spawn mechanism degrades. The state file becomes the explicit
  hand-off record between turns; the user prompts the next sub-step
  with the task index.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strict sequential per-task handoff already matches that
  constraint.
- **Cursor** has no per-agent allowlist; per-task scope (Cut not
  inventing edge cases, Cook not touching later-task files, Press not
  chasing prior-task regressions) is enforced solely by prompt on
  Cursor (each agent's Permission Contract block plus the per-task
  prompt's "task <N> only" framing is the backstop).

In every harness, the four stage agents (`cut`, `cook`, `press`, plus
the `age` skill) ARE the portable surface — the Agent/Skill invocations
are the Claude-flavored binding. The state file is harness-agnostic
JSON; any harness can read and resume against it.

## Deferred behavior

The dispatch protocol above is now wired. Three enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Cook's no-test-edit
  invariant, Cut's no-production-edit invariant, and Press's
  no-production-edit invariant are currently enforced only by each
  agent's Permission Contract prompt and the source-frontmatter
  `disallowedTools` list. The compiler does not yet propagate
  `disallowedTools` / `permissionMode` into the rendered harness
  frontmatter, so on Claude Code these invariants are prompt-only at
  runtime.
- **Per-task scope enforcement** — Cook's "no editing files reserved
  for tasks > N" and Press's "no chasing prior-task regressions" are
  currently enforced only by the per-task prompt. A first-class
  `--scope` flag on cook/press source frontmatter (or a per-task
  worktree analogous to `/fromagerie`'s atom worktrees) would make
  this structural rather than prompt-only.
- **Loop counter persistence** — `fix_loop_attempts` in the state file
  IS durable (this is the only counter we persist) but the cycle
  counter for "which task we're walking right now" lives only in
  orchestrator context. If the Incremental session is resumed in a
  fresh context the orchestrator must re-read the state file and
  resume from the first non-`done` task — which is exactly the
  resume-from-pending behaviour, so this gap is mostly closed.

The first two gaps lower **Cross-cutting principle: Permission model
per stage** on the scoreboard, not Flow 6 itself.
