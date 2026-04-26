---
name: incremental
description: Incremental flow entry point. Walks a spec or task list one task at a time through Cook → Cut → Press → Age, looping until the backlog is exhausted or a stop condition fires. Each task's Culture is folded into Cook as minimal targeted grounding — no per-iteration full-repo scan.
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

```
Per task N:
  Cook (read task-N + minimal grounding) → Cut (decompose task) → Press (execute) → Age (verify)
                                                                                       │
                                                                                       ▼
                                                                                   next task
```

```
[Cook task-1 → Cut → Press → Age] →
[Cook task-2 → Cut → Press → Age] →
[Cook task-3 → Cut → Press → Age] → … until backlog exhausted or stop fires
```

Culture is **not run as a separate per-task stage**. The Quintessential
flow specifies per-iteration Culture must be *minimal* — just enough to
ground the agent in patterns relevant to the current task. That grounding
is folded into Cook (which reads only the spec entry, the files the task
names, and the immediate neighbours). A full repo scan per task is the
exact cost spike this flow is designed to avoid.

If the spec was authored without a Culture pre-pass and the agent cannot
ground a task at all, halt the loop and recommend `/culture` or `/mold`
on the spec before retrying. Do not silently expand Cook into Culture.

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
| Cook (per task) | Plan task-N + minimal targeted grounding | `cheez-search`/`cheez-read` scoped to task-named files and immediate callers; `Write` to a task-plan file under `$TMPDIR/incremental-<slug>-task-<N>.md` | Full-repo scans; reading unrelated slices; rewriting the spec; merging tasks |
| Cut | Decompose task into atomic edits | `Write` to the task-plan file extending it with an ordered edit list; `cheez-search`/`cheez-read` for the named files | Production-file edits; widening scope beyond the task; pulling work forward from later tasks |
| Press | Execute the edit list | `cheez-write`, full Bash for build/test, `gh` for status reads | Editing files outside Cut's edit list; touching files belonging to later tasks; rebasing |
| Age | Verify | The standard `/age` six-dimension review, **scoped to the task's net diff only** | Re-opening the design conversation; widening scope to other tasks; reviewing the whole spec |

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

## Per-task fix loop

If Age surfaces findings >= 50 on a task, loop back to **Press** (not
Cook, not Cut) for that same task. The decomposition is presumed correct;
only the implementation needs to converge.

A single task may cycle Press → Age at most **three** times before the
loop halts and the task is marked `failed` in the state file. The
backlog walk does not silently skip past a failed task — it stops and
returns control to the user with the cumulative findings for that task.

## Cross-task hand-off

Between tasks N and N+1:

1. Press for task N must be green (build + tests pass).
2. Age for task N must return no findings >= 50.
3. The state file is updated to mark task N `done`.
4. Cook for task N+1 starts fresh — it does NOT inherit Cook's plan
   buffer from task N. Each task plans against its own slice of the
   spec to prevent context bleed.

This is the discipline that keeps the flow's per-task cost roughly
constant instead of growing with N.

## Dispatch contract

1. **Resolve `$ARGUMENTS`** to a concrete spec or task list. Accept
   `<harness>/specs/<slug>.md`, an absolute path, an issue reference with
   an embedded checklist, or a path to a markdown file with `- [ ]`
   checkbox tasks. If the spec is unparseable, halt and ask for a
   structured task list.
2. **Classify** the task list. If tasks look independent and parallel,
   recommend `/fromagerie` instead and ask for confirmation before
   continuing in sequential mode.
3. **Announce** the planned flow path (`Cook → Cut → Press → Age` per
   task, looped) and the total task count.
4. **Pause** for confirmation. The user may redirect, narrow the task
   range (e.g. "tasks 3–5 only"), or abort.
5. **Walk the backlog.** For each pending task in order, dispatch the
   four stages. Update the state file after each stage transition.
6. **Per-task fix loop.** On Age findings >= 50, loop Press → Age up to
   three times before halting on that task.
7. **Cross-task break.** After every task, surface a one-line status
   ("task N/M done, M-N tasks remaining") so the user can interrupt
   without losing visibility.

## Stop conditions

`/incremental` stops when **any** of the following is true:

- The backlog is exhausted — every task is `done`. Return the cumulative
  Age summary.
- A task fails the three-loop Press → Age cap → halt with cumulative
  findings for that task; state file marks it `failed`. Resume after
  human direction.
- Age cannot be run on a task because Press is not green → halt; do not
  silently advance to the next task.
- The user interrupts between tasks → exit cleanly; the state file
  reflects the next pending task for the next invocation.
- A task requires Culture-level discovery (Cook cannot ground without a
  full repo scan) → halt and recommend `/culture` or `/mold` on the
  spec; do not silently expand Cook.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/<stage>-<slug>-task-<N>.md`. The orchestrator works from
summaries; the next stage may read the prior stage's full report if it
needs deeper context. This keeps the orchestrator's window small even
across a long backlog walk.

## Deferred behavior

> **Scaffold notice.** The per-task loop, the state file, and the
> three-loop Press → Age cap are not yet wired. This file documents the
> contract. The current implementation should resolve the spec, classify
> the task list, announce the planned walk, pause for confirmation, and
> stop — it does not yet spawn the stage agents or persist state.

The next iteration will:

- Wire the per-task four-stage dispatch via the `Skill` / `Agent` tools.
- Implement the JSON state file at `$TMPDIR/incremental-<slug>-state.json`
  and the resume-from-pending behaviour.
- Enforce the per-task scope constraints at the tool layer (Press's edit
  list limits, Age's diff scoping).
- Implement the three-loop Press → Age cap and the failed-task halt.
- Add the `/fromagerie` redirect heuristic for independent-parallel
  task lists.
