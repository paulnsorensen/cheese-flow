---
name: fromage
description: Spec-First flow entry point. Routes a known, fully-specified feature through Cook (read spec + light grounding) → Cut (decompose) → Press (execute) → Age (review). Culture is intentionally minimal — the spec is the source of truth, not a fresh codebase scan.
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

```
Cook (read spec + light surface scan) → Cut (decompose) → Press (execute) → Age (review)
       ↑
   Culture is folded into Cook's pre-pass — no full repo scan, no
   architectural exploration. Cook reads the spec, the files the spec
   names, and their immediate neighbours.
```

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
the spec already encodes the architectural decision. Cook's pre-pass is
scoped to:

- The spec body itself (Problem, Goals, Non-goals, Approach, Risks,
  Quality gates, Open questions).
- The files named in the spec's Approach section.
- Their immediate callers and dependencies, surfaced via `cheez-search`
  and `cheez-read` (outline mode).

If Cook cannot ground without a broader scan — for example because the
spec's Approach is too vague to act on — halt and redirect to `/mold` or
`/explore`. Do not silently expand into a Culture stage; that is a
different flow.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Cook | Read spec + light grounding + plan | `cheez-search`, `cheez-read` scoped to spec-named files and immediate neighbours; `Write` to `$TMPDIR/fromage-<slug>-plan.md` (the plan, never production) | Production-file edits; full-repo scans; renegotiating the spec; adding goals not in the spec; dropping non-goals |
| Cut | Decompose the plan | `Write` to `$TMPDIR/fromage-<slug>-tasks.md` extending Cook's plan with an ordered edit list; `cheez-search`/`cheez-read` for surface mapping | Production-file edits; widening scope beyond the spec; pulling in adjacent improvements |
| Press | Execute the edit list | `cheez-write`, full Bash for build/test, `gh` for status reads | Editing files outside Cut's edit list; refactoring untouched code; rebasing or force-pushing without explicit user approval |
| Age | Review the net diff | The standard `/age` six-dimension review, scoped to the spec's net diff and verified against the spec's Quality gates | Re-opening the design conversation; widening scope beyond the spec |

## Dispatch contract

1. **Resolve `$ARGUMENTS`** to a concrete spec. Accept
   `<harness>/specs/<slug>.md`, an absolute path to a markdown file with
   the `/mold` skeleton, or an inline spec body. If the input is a rough
   idea or incomplete spec, redirect to `/mold` and stop.
2. **Validate the spec.** It must contain at minimum the Approach and
   Quality gates sections. If either is missing, halt and redirect to
   `/mold` to complete the spec before execution. Do not proceed on a
   half-specified plan — that is the failure mode this flow is designed
   to avoid.
3. **Classify the shape.** If the Approach section enumerates many
   independent units of work (typically >= 4 non-overlapping atoms),
   recommend `/fromagerie` and ask for confirmation before continuing in
   single-feature mode. If it enumerates a linear per-task backlog,
   recommend `/incremental`.
4. **Announce** the planned flow path (`Cook → Cut → Press → Age`,
   Culture folded into Cook) and the spec's Quality gates (the exact
   commands Age will verify).
5. **Pause** for confirmation. The user may redirect, narrow scope, or
   abort. Until confirm, no production file is touched.
6. **Dispatch** the four stages sequentially. Each stage hands off via
   the structured summary contract documented on its agent
   (`agents/<stage>.md.eta`). Cook's plan file becomes Cut's input;
   Cut's task list becomes Press's input; Press's net diff becomes Age's
   scope.
7. **Loop on Age failure** — if Age surfaces findings >= 50, loop back to
   **Press** (not Cook, not Cut). The plan and decomposition are presumed
   correct because the spec was the source of truth; only the
   implementation needs to converge. A failed Age that challenges the
   spec itself halts the flow and recommends `/mold` to revise the spec.

## Stop conditions

`/fromage` stops when **any** of the following is true:

- Age returns no findings >= 50, Press is green, and the spec's Quality
  gates pass → success. Surface the cumulative summary and the net diff.
- The spec is missing required sections (Approach or Quality gates) → halt
  and recommend `/mold`. No Cook work occurs.
- Cook cannot ground the plan against the named files (spec is too vague
  or names files that do not exist) → halt and recommend `/mold` or
  `/explore`. Do not silently expand Cook into a full Culture pass.
- A Press → Age fix attempt cycles more than **three** times without
  converging → halt and return cumulative findings. Further work needs
  human direction or a fresh `/mold` to revise the spec.
- Age findings call the spec itself into question (not just the
  implementation) → halt; the spec is invalidated and the user is asked
  whether to re-enter `/mold` or abort. The locked-spec assumption of
  this flow is broken — continuing would compound the error.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/<stage>-fromage-<slug>.md`. The orchestrator works from
summaries; the next stage may read the prior stage's full report if it
needs deeper context. This keeps the orchestrator's window small across
the four stages.

## Deferred behavior

> **Scaffold notice.** Stage dispatch, the spec-validation gate, the
> single-feature-vs-fromagerie classifier, and the Press → Age fix loop
> are not yet wired. This file documents the contract. The current
> implementation should resolve `$ARGUMENTS` to a spec, validate that
> Approach and Quality gates exist, announce the planned flow, pause for
> confirmation, and stop — it does not yet spawn the stage agents.

The next iteration will:

- Wire the four-stage dispatch via the `Skill` / `Agent` tools.
- Implement the spec-validation gate that requires Approach and Quality
  gates before Cook starts.
- Add the parallel-atoms classifier that redirects to `/fromagerie` when
  the spec decomposes into >= 4 non-overlapping units of work.
- Enforce Cook's no-production-write invariant and Cut's plan-only
  output at the tool layer (no `Edit`/`Write` on production files until
  Press) — not just by prompt.
- Implement the three-loop cap on Press → Age and the spec-invalidation
  halt when Age challenges the spec itself.
