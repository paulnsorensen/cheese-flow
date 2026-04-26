---
name: age
description: Review flow entry point. Routes nominally-complete code (PR, branch diff, module) through Culture (read-only diff + PR ingest) → Age (six-dimension review) → optional Press fix-loop → Age (re-review), explicitly skipping Cook and Cut. Also reusable as the standalone review primitive inside other flows.
argument-hint: "[--comprehensive] [--scope <path>] [--no-fix] [<PR# | diff ref | branch | path>]"
---

# /age

`/age` is the entry point for the **Review Flow** (Flow 5 of the seven
canonical cheese-flow flows) and the standalone Staff Engineer review
primitive used by every other flow. The agent's role is critic, not
author: review sub-agents write findings, not fixes. The orchestrator
then either approves or spawns a bounded fix loop that re-enters Press.

## Flow

```
Culture (ingest diff + PR + spec) → Age (six dimensions in parallel)
                                        │
                            findings >= 50?
                              ├── no  → success
                              └── yes → Press (fix only the surfaced findings) → Age (re-review)
                                          (capped at three loops)
```

```
                      ┌──── Cook is skipped ─────┐
                      │                          │
Culture ──────────────┴──── Cut is skipped ──────┴──► Age ⇄ Press
```

Cook and Cut are **deliberately skipped**. The plan is encoded in the
existing diff or module; the question is whether it is good, not what to
build. Inviting Cook back in widens scope — that is `/fromage` or
`/explore` territory, not Review.

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Diagnose a failure (root cause, not quality) | `/debug` |
| Finish a stalled PR (not just review it) | `/pr-finish` |
| Build new code from a spec | `/fromage` |
| Talk through architecture without commitment | `/culture` |

`/age` assumes the code is **done enough to evaluate**. If it is not, the
flow halts at the Culture pre-pass and recommends `/pr-finish` or
`/debug`.

## Modes

| Mode | Trigger | Scope |
|---|---|---|
| Focused (default) | no flag | Recent changes on the current branch, or an explicit diff / change ref |
| Comprehensive | `--comprehensive` | Full module audit against the spec and engineering principles |
| Scoped | `--scope <path>` | A specific file, folder, or glob |
| Review-only | `--no-fix` | Suppress the Age→Press fix loop; return findings and stop |

The `--no-fix` flag is the contract used when `/age` is invoked **as a
sub-step of another flow** (`/debug`, `/pr-finish`, `/fromage`,
`/incremental`, `/explore`). Those flows already own the fix loop; the
embedded `/age` call must surface findings and return without spawning
its own Press cycle.

## Culture pre-pass (the Flow 5 grounding step)

Before any review dimension runs, Culture performs a single read-only
ingest pass to anchor the review in context. Its output is a structured
brief that every Age dimension reads from `$TMPDIR/age-<slug>-context.md`.

The brief MUST include (when available):

- The PR number, branch, and base ref the diff is against.
- The PR description and any linked spec under `<harness>/specs/`.
- The net diff surface (file list, change shape per file).
- Failing CI checks (`gh pr checks`) or open review threads, if any.
- Any prior Age reports for the same PR (so a re-review knows what was
  already surfaced and what was newly introduced).

If Culture finds the change is too divergent or under-specified to
review (no diff, no PR, no spec, contradictory commits) it halts and
recommends `/pr-finish` or `/mold` instead of forcing Age in.

## Review dimensions

After Culture's brief is on disk, six dimensions run as independent
parallel sub-agents. All findings use a 0-100 confidence scale; only
>= 50 is surfaced to the user.

| Dimension | Sub-agent | What it looks for |
|---|---|---|
| Safety | `fromage-age-safety` | Bugs, security holes, silent failures, unchecked inputs |
| Architecture | `fromage-age-arch` | Complexity budgets (lines, params, nesting), Sliced Bread organization |
| Encapsulation | `fromage-age-encap` | Leaky abstractions, overly wide public APIs, cross-boundary imports |
| YAGNI / de-slop | `fromage-age-yagni` | Unjustified dead code, speculative abstractions, AI-generated noise |
| Spec adherence | `fromage-age-spec` | Drift from `<harness>/specs/<slug>.md`, monkey patches, shortcuts |
| History risk | `fromage-age-history` | Per-file risk modifiers derived from git blame / churn patterns |

`<harness>` is the active harness output root — `.claude` for Claude
Code, `.codex` for Codex, `.cursor` for Cursor, `.copilot` for Copilot
CLI.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture (pre-pass) | Read-only ingest | `gh pr view`, `gh pr diff`, `gh pr checks`, `Bash(git log:*)`, `Bash(git diff:*)`, `cheez-search`, `cheez-read`, `briesearch`; `Write` only to `$TMPDIR/age-<slug>-context.md` | Any `Edit`, `Write` outside `$TMPDIR`, `NotebookEdit`, or git-mutating Bash on production files |
| Age (six dimensions) | Annotate-only critic | `cheez-search`, `cheez-read`, `Bash(git log:*)`, `Bash(git diff:*)`, `tilth_*` queries; `Write` only to `$TMPDIR/age-<slug>-<dimension>.md` | Any `Edit`/`cheez-write` on production files; spawning fix sub-agents; rewriting tests; touching `.claude`, `.codex`, `.cursor`, `.copilot` |
| Press (fix loop, opt-in) | Bounded fixer | `cheez-write` on the files Age cited; full Bash for build/test; `gh` for status reads | Touching files Age did not cite; widening scope; new features; refactors unrelated to surfaced findings; rebasing or force-pushing without explicit user approval |

The Culture and Age stages are **read-only on production files** by
contract. Press is the only stage that may write to source. This is the
permission backstop that distinguishes review from authorship.

## Output contract

`/age` returns a single Age Report with:

- A one-line summary per dimension.
- Findings grouped by severity, each including the dimension, score,
  rationale, and a `file_path:line_number` anchor the user can jump to.
- History-risk modifiers applied to sibling findings (not surfaced on
  their own).
- A clear "no significant findings" result if all dimensions return
  scores below 50.

When the fix loop runs, the report appends a per-loop delta showing
which findings cleared, which persisted, and any new findings the
re-review introduced.

## Dispatch contract

1. **Resolve `$ARGUMENTS`** to a concrete review target. Accept `<PR#>`,
   `<branch>`, a diff ref (`HEAD~3..HEAD`), a path, or empty (= recent
   changes on the current branch). If none resolve, halt and ask.
2. **Classify** the input as review-shaped. If the input is actually a
   bug report, redirect to `/debug`. If it is a stalled PR with missing
   work, redirect to `/pr-finish`. If it is a fresh feature with no
   code, redirect to `/mold` or `/fromage`.
3. **Announce** the planned flow path (`Culture → Age → [Press → Age]?`,
   Cook and Cut skipped) and the read-only invariant on Culture and
   Age. State whether the fix loop is enabled (default) or suppressed
   (`--no-fix`).
4. **Pause** for confirmation. The user may redirect or supply
   additional review context (linked spec, related PRs, focus areas)
   before Culture begins.
5. **Run Culture pre-pass.** Culture writes its brief to
   `$TMPDIR/age-<slug>-context.md` and surfaces a one-line summary. If
   Culture halts (under-specified target), the flow returns the
   recommendation and stops.
6. **Spawn the six dimension sub-agents in parallel** via the `Agent`
   tool. Each reads Culture's brief, runs its protocol, and writes its
   full findings to `$TMPDIR/age-<slug>-<dimension>.md` while returning
   a compact summary (top findings + dimension score) to the
   orchestrator.
7. **Aggregate** findings, apply the 50-point surface threshold, fold
   history-risk modifiers into sibling findings, and emit the unified
   Age Report.
8. **Fix loop (opt-in).** If `--no-fix` is set, stop here. Otherwise,
   if any finding scores >= 50, ask the user via `AskUserQuestion`
   whether to spawn Press to fix the surfaced findings. On confirm,
   dispatch Press scoped to the cited files only, then re-run the six
   Age dimensions for a delta-only re-review.

## Stop conditions

`/age` stops when **any** of the following is true:

- Age returns no findings >= 50 (or only history-risk modifiers) →
  success; no fix loop is offered.
- `--no-fix` was set → return the Age Report and stop, regardless of
  finding count. The caller (another flow) owns the fix decision.
- The user declines the fix-loop prompt → return the Age Report and
  stop.
- Culture's pre-pass cannot find a reviewable target with confidence
  >= 50 → halt and recommend `/pr-finish` or `/mold`.
- The Press → Age fix loop runs more than **three** times without
  converging → halt and return cumulative findings; further work needs
  human direction or a fresh `/explore` / `/mold`.
- Age findings call the spec or design itself into question (not just
  the implementation) → halt; the fix loop is invalidated and the user
  is asked whether to enter `/mold` (rewrite the spec) or `/explore`
  (rethink the approach).

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/age-<slug>-<stage>[-loop-<N>].md`. The orchestrator works from
summaries; the next stage may read the prior stage's full report if it
needs deeper context. This keeps the orchestrator's window small even
across a three-loop fix cycle.

## Deferred behavior

> **Scaffold notice.** The Culture pre-pass, the parallel six-dimension
> dispatch, the `AskUserQuestion`-gated fix loop, and the three-loop cap
> are not yet wired. This file documents the contract. The current
> implementation should announce the planned flow, pause for
> confirmation, and stop — it does not yet spawn the stage agents.

The next iteration will:

- Wire the Culture pre-pass and persist its brief under
  `$TMPDIR/age-<slug>-context.md`.
- Spawn the six dimension sub-agents in parallel via the `Agent` tool
  and aggregate their structured summaries.
- Implement the `AskUserQuestion`-gated Press fix loop, scoped to the
  cited files only, with the three-loop convergence cap.
- Enforce Culture's and Age's no-production-write invariants at the
  tool layer (no `Edit`, `cheez-write`, `NotebookEdit`, or git-mutating
  Bash) — not just by prompt.
- Implement the spec-invalidation halt path that recommends `/mold` or
  `/explore` when Age findings undermine the design itself.
