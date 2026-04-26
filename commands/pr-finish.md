---
name: pr-finish
description: PR-Finish flow entry point. Routes a partially-done branch (WIP, stalled PR, missing tests, post-rebase fallout) through Culture (read diff + PR context) → Cut (identify remaining tasks) → Press (execute) → Age (review), explicitly skipping Cook.
argument-hint: "<PR# | branch name | diff ref | path to WIP description>"
---

# /pr-finish

`/pr-finish` is the entry point for the **PR-Finish / Continuation Flow**
(Flow 4 of the seven canonical cheese-flow flows). Use it when a branch
already contains in-progress work and you want the agent to complete,
extend, or clean it up before merge.

## Flow

```
Culture (read diff + PR context) → Cut (identify remaining tasks) → Press (execute) → Age (review)
                                  └─────── Cook is skipped ───────┘
```

Cook is **deliberately skipped**. The plan is already encoded in the diff,
the PR description, and any failing CI checks. Re-cooking from scratch
would discard the existing direction and invent a new spec; that is
`/mold` + `/fromage` territory, not PR-Finish.

If Culture concludes the existing work is too divergent or under-specified
to finish (no PR description, no spec link, contradictory commits), the
flow halts and redirects to `/mold` instead of forcing a Cook stage in.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture | Read-only ingest | `gh pr view`, `gh pr diff`, `gh pr checks`, `Bash(git log:*)`, `Bash(git diff:*)`, `cheez-search`, `cheez-read`, `briesearch` | Any `Edit`, `Write`, `NotebookEdit`, or git-mutating Bash |
| Cut | Decompose remaining work | `Write` to a single task-list file under `$TMPDIR/pr-finish-<slug>.md`; `cheez-search`/`cheez-read` for surface mapping | Production-file edits; new spec authoring; widening scope beyond the PR's stated goal |
| Press | Execute the task list | `cheez-write`, full Bash for build/test, `gh pr` for status reads | Touching files outside Cut's task list; rebasing or force-pushing without explicit user approval |
| Age | Review | Standard `/age` six-dimension review, scoped to the PR's net diff (base..HEAD) | Re-opening the design conversation; expanding scope beyond the PR |

## Approval gate (between Cut and Press)

The defining constraint of this flow: **Cut surfaces a structured task
list and pauses for human approval before Press touches any production
file.** This is the only flow where the human-in-the-loop gate is between
Cut and Press rather than at flow entry. The reason: the human already
opened the PR and signalled intent; the open question is whether the
remaining-work decomposition matches their expectation.

The approval prompt MUST include:

1. The PR number / branch under continuation.
2. Cut's task list (numbered, with file targets).
3. The merge-readiness checklist Press will run before declaring done
   (build green, CI checks green, no merge conflicts with base).
4. An explicit confirm/abort/edit choice via `AskUserQuestion`.

## Dispatch contract

1. **Resolve `$ARGUMENTS`** to a concrete branch + PR. Accept `<PR#>`,
   `<branch>`, a diff ref (`HEAD~3..HEAD`), or a path to a WIP description.
   If none resolve, halt and ask for a PR or branch.
2. **Classify** the input as continuation-shaped. If the PR has no
   commits or no description and the user is actually starting from
   scratch, redirect to `/mold` or `/cheese`.
3. **Announce** the planned flow path (`Culture → Cut → Press → Age`,
   Cook skipped) and the read-only invariant on Culture.
4. **Pause** for confirmation. The user may redirect or supply additional
   context (linked spec, related PRs, CI failure links) before Culture
   begins.
5. **Dispatch** the four stages sequentially. Each stage hands off via
   the structured summary contract documented on its agent
   (`agents/<stage>.md.eta`). Culture's report MUST include the PR's
   stated goal, the current diff surface, the failing-checks list (if
   any), and any open review threads before Cut starts.
6. **Approval gate** — Cut writes its task list to
   `$TMPDIR/pr-finish-<slug>.md`, surfaces it inline, and waits for
   explicit user approval via `AskUserQuestion`. Press does NOT start
   without confirm.
7. **Loop on Age failure** — if Age surfaces findings >= 50, loop back to
   Press (not Cut). Re-running Cut for a fix-loop is wasteful unless the
   findings change the task decomposition.

## Stop conditions

`/pr-finish` stops when **any** of the following is true:

- Age returns no findings >= 50, Press is green, and CI checks on the PR
  are green → success.
- Culture concludes the PR is too divergent / under-specified to finish
  (confidence >= 50 that this is not a continuation problem) → halt and
  recommend `/mold`.
- The user rejects Cut's task list at the approval gate → halt and return
  the task list for editing; no Press work occurs.
- A fix attempt cycles through Press → Age more than **three** times
  without converging → halt and return the cumulative findings. Further
  work needs human direction or a fresh `/mold`.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/<stage>-<slug>.md`. The orchestrator works from summaries; the
next stage may read the prior stage's full report if it needs deeper
context. This keeps the orchestrator's window small across the four
stages.

## Deferred behavior

> **Scaffold notice.** Stage dispatch, the Cut→Press approval gate, and
> the Press→Age fix loop are not yet wired. This file documents the
> contract. The current implementation should announce the planned flow,
> pause for confirmation, and stop — it does not yet spawn the stage
> agents.

The next iteration will:

- Wire the four-stage dispatch via the `Skill` / `Agent` tools.
- Implement the `AskUserQuestion`-gated approval between Cut and Press.
- Enforce Culture's read-only invariant and Press's no-rebase-without-
  approval invariant at the tool layer (not just by prompt).
- Implement the three-loop cap on Press → Age and halt with cumulative
  findings if convergence fails.
