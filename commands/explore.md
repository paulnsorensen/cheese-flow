---
name: explore
description: Exploration flow entry point. Routes a fuzzy problem (unclear goals, no spec) through Culture (broad context) ↔ Cook (propose approaches) iterative loop, then a hard human-in-the-loop approach lock, then Cut → Press → Age. Distinct from /culture (talk-only) and /mold (spec-only) — /explore commits to building once an approach is locked.
argument-hint: "<fuzzy problem | open question | architectural spike | half-formed idea>"
---

# /explore

`/explore` is the entry point for the **Exploration Flow** (Flow 2 of the
seven canonical cheese-flow flows). Use it when the problem is real but the
solution shape is unclear — you want the agent to discover the right
approach with you, then build it once you both agree.

This is the only flow whose Culture stage is **iterative**. Every other
flow uses Culture as a single read-only pre-pass; here, Culture and Cook
loop together until an approach locks.

## Flow

```
Culture (broad scan) ⇄ Cook (propose ≥2 approaches with trade-offs)
                          │
                  approach lock (AskUserQuestion gate)
                          │
                          ▼
                   Cut → Press → Age
```

```
Culture-1 → Cook-1 (alternatives + trade-offs)
   ↑           │
   └───────────┘  (loop on new questions, capped)
                          │
                  ── lock approach ──
                          │
                          ▼
                   Cut → Press → Age
```

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Talk it out with no commitment to build | `/culture` |
| Write a spec and stop (no execution) | `/mold` |
| Build a known spec end-to-end | `/fromage` (or `/fromagerie` for parallel atoms) |
| Walk an existing backlog of tasks | `/incremental` |

`/explore` is the bridge between thinking and building. The spec is a
**byproduct** of the Culture↔Cook loop, not the entry artifact. If you
already have a spec, skip to `/fromage`. If you only want to think, stay
in `/culture`.

## The Culture↔Cook loop

The loop is the thing this flow exists to make safe. Each cycle:

1. **Culture pass.** Scan the surface area named in the prompt or by the
   prior Cook pass. Read-only — no production writes. Returns a
   structured map (files involved, current behaviour, prior art links).
2. **Cook pass.** Synthesize what Culture found into **at least two**
   candidate approaches. Each approach must include: scope, file impact,
   risk, and an honest "why not" against the alternatives. "Do nothing"
   is always a candidate.
3. **Branch decision.** If Cook surfaces a question that requires deeper
   grounding (e.g. "approach A only works if behaviour X is true"), loop
   back to Culture for a targeted second pass. Otherwise, advance to the
   approach lock.

The loop cap is **three cycles**. After the third Culture↔Cook pass, the
flow halts and presents whatever alternatives are on the table — even if
trade-offs are still ambiguous. This is the cost-control gate: without
it the agent can iterate indefinitely and burn tokens without committing.

## Approach lock (the hard gate)

Cook's final pass writes an **approach-lock proposal** to
`$TMPDIR/explore-<slug>-approach.md` and presents it via `AskUserQuestion`
with three choices:

1. **Lock approach N** → flow advances into Cut.
2. **Loop again** (only if cycles remain) → return to Culture with a
   user-supplied focusing question.
3. **Abort** → return the proposal as a hand-off to `/mold` (write the
   spec) or `/culture` (keep thinking) without entering Press.

The proposal MUST include:

- The chosen approach, named.
- The rejected alternatives, with the one-line reason each was rejected.
- The file impact list Cut will use as its decomposition input.
- The Quality gates (commands that must pass for Age to clear).
- The unresolved questions (if any) Press must surface during execution.

No production file is touched until the lock fires. This is the
architectural backstop against the "agent never commits, costs escalate"
failure mode the Quintessential flow doc calls out for this flow.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture (per cycle) | Read-only context gathering | `cheez-search`, `cheez-read`, `briesearch`, `Bash(git log:*)`, `Bash(git diff:*)`, `Bash(ls:*)`, sandboxed log/repro runs | Any `Edit`, `Write`, `NotebookEdit`, or git-mutating Bash on production files |
| Cook (per cycle) | Propose alternatives with trade-offs | `Write` to `$TMPDIR/explore-<slug>-cook-<N>.md` only; `cheez-search`/`cheez-read` to validate approach claims | Production-file edits; locking on a single approach without surfacing the alternatives; skipping the "Do nothing" candidate |
| Cut | Decompose locked approach | `Write` to `$TMPDIR/explore-<slug>-tasks.md`; `cheez-search`/`cheez-read` for surface mapping | Production-file edits; widening scope beyond the locked approach; reopening the approach decision |
| Press | Execute the task list | `cheez-write`, full Bash for build/test, `gh` for status reads | Editing files outside Cut's task list; reopening the approach decision; folding rejected alternatives back in |
| Age | Review | Standard `/age` six-dimension review, scoped to the net diff | Re-opening the design conversation; widening scope beyond the locked approach |

## Dispatch contract

1. **Classify** `$ARGUMENTS` to confirm exploration shape (fuzzy problem,
   no clear solution, no existing spec). If the input is a spec path,
   redirect to `/fromage`. If it is a bug or stack trace, redirect to
   `/debug`. If it is a question with no intent to build, redirect to
   `/culture`. If it is a feature description with a clear approach
   already, redirect to `/mold` then `/fromage`.
2. **Announce** the planned flow path (Culture↔Cook loop with a
   three-cycle cap, then Cut → Press → Age) and the no-writes invariant
   on Culture and Cook.
3. **Pause** for confirmation. The user may redirect or supply additional
   focusing context before the first Culture pass.
4. **Walk the loop.** Dispatch Culture → Cook for up to three cycles.
   Each cycle ends by either (a) requesting another Culture pass with a
   focusing question, or (b) advancing to the approach lock.
5. **Approach lock.** Cook's final pass writes the approach-lock proposal
   and waits for explicit user choice via `AskUserQuestion`. No
   production file is touched until lock fires.
6. **Dispatch Cut → Press → Age** sequentially after lock. Each stage
   hands off via the structured summary contract on its agent
   (`agents/<stage>.md.eta`).
7. **Loop on Age failure** — if Age surfaces findings >= 50, loop back to
   **Press** (not Cook, not Culture). The locked approach is presumed
   correct; only the implementation needs to converge. A failed Age that
   challenges the approach itself halts the flow and returns control to
   the user with a recommendation to re-enter `/explore` or `/mold`.

## Stop conditions

`/explore` stops when **any** of the following is true:

- Age returns no findings >= 50 and Press is green → success. The
  approach-lock proposal becomes the de-facto spec record (the user may
  promote it to `<harness>/specs/` via `/mold` if they want it
  versioned).
- The user picks **Abort** at the approach lock → halt with the
  approach-lock proposal as a hand-off; no Press work occurs.
- The Culture↔Cook loop hits the three-cycle cap with no convergent
  approach → halt and surface the alternatives on the table; recommend
  `/culture` or `/mold` for further exploration.
- A Press → Age fix attempt cycles more than **three** times without
  converging → halt and return cumulative findings; further work needs
  human direction or a fresh `/explore` cycle.
- Age findings call the locked approach itself into question (not just
  the implementation) → halt; the approach lock is invalidated and the
  user is asked whether to re-enter the loop or abort.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR/<stage>-explore-<slug>[-cycle-<N>].md`. The orchestrator works
from summaries; the next stage may read the prior stage's full report if
it needs deeper context. This keeps the orchestrator's window small even
across the three-cycle loop.

## Deferred behavior

> **Scaffold notice.** The Culture↔Cook loop, the three-cycle cap, the
> approach-lock `AskUserQuestion` gate, and the Cut → Press → Age
> dispatch are not yet wired. This file documents the contract. The
> current implementation should classify `$ARGUMENTS`, announce the
> planned loop, pause for confirmation, and stop — it does not yet
> spawn the stage agents or persist the approach-lock proposal.

The next iteration will:

- Wire the Culture↔Cook loop with the three-cycle cap, persisting each
  cycle's report under `$TMPDIR/explore-<slug>-cycle-<N>.md`.
- Implement the `AskUserQuestion`-gated approach lock between Cook and
  Cut, with the three-choice menu (lock / loop again / abort).
- Enforce Culture's and Cook's no-production-write invariants at the
  tool layer (no `Edit`, `Write` outside `$TMPDIR`, `NotebookEdit`, or
  git-mutating Bash) — not just by prompt.
- Implement the three-loop cap on Press → Age and the
  approach-invalidation halt when Age challenges the approach itself.
- Add the redirect heuristics to `/fromage`, `/mold`, `/debug`, and
  `/culture` based on classifier confidence.
