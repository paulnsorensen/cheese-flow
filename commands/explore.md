---
name: explore
description: Exploration flow entry point. Routes a fuzzy problem (unclear goals, no spec) through Culture (broad context) ⇄ Cook (propose approaches) iterative loop, then a hard human-in-the-loop approach lock, then Cut → Cook → Press → Age. Distinct from /culture (talk-only) and /mold (spec-only) — /explore commits to building once an approach is locked.
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

The canonical Exploration flow in the design doc is `Culture → Cook
iterative → Cut → Press → Age`. The cheese-flow agent ecosystem maps
those pipeline phases to TDD-flavored sub-agent roles, identical to
`/fromage` once the approach has locked:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Discover (loop) | `culture` sub-agent (per cycle) | Read-only repo scan scoped to the current question |
| Propose (loop) | `cook` sub-agent (per cycle, propose-only mode) | Synthesise ≥2 candidate approaches with trade-offs to `$TMPDIR` only |
| Approach lock | Orchestrator (`AskUserQuestion`) | User picks the approach; the proposal becomes the de-facto plan |
| Define contract | `cut` sub-agent | Write failing tests pinning the locked approach's named obligations |
| Execute | `cook` sub-agent (impl mode) | Production code that turns Cut's red tests green |
| Adversarial verify | `press` sub-agent | Post-impl boundary / chaos / integration tests |
| Review | `age` skill | Six-dimension merged review |

So the **actual sub-agent dispatch order** is the loop (`Culture → Cook`
× up to 3) → lock → `Cut → Cook → Press → Age`. The two Cook passes are
distinct: in the loop, Cook is forbidden from production writes (it
emits the proposal to `$TMPDIR` only); after the lock, Cook is the
standard production-code writer per its Permission Contract.

```
Culture-1 → Cook-1 (alternatives + trade-offs)
   ↑           │
   └───────────┘  (loop on new questions, capped at 3 cycles)
                          │
                  ── approach lock (AskUserQuestion) ──
                          │
                          ▼
                Cut → Cook → Press → Age
```

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Talk it out with no commitment to build | `/culture` |
| Write a spec and stop (no execution) | `/mold` |
| Build a known spec end-to-end | `/fromage` (or `/fromagerie` for parallel atoms) |
| Walk an existing backlog of tasks | `/incremental` |
| Continue a partially-done PR | `/pr-finish` |
| Fix a bug | `/debug` |

`/explore` is the bridge between thinking and building. The spec is a
**byproduct** of the Culture↔Cook loop, not the entry artifact. If you
already have a spec, skip to `/fromage`. If you only want to think, stay
in `/culture`.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture (per cycle) | Read-only context gathering | `cheez-search`, `cheez-read`, `briesearch`, `Bash(git log:*)`, `Bash(git diff:*)`, `Bash(ls:*)`, sandboxed log/repro runs, `Write` to `$TMPDIR/explore-<slug>-culture-c<N>.md` | Any production-file `Edit` / `Write` / `NotebookEdit`, or git-mutating Bash |
| Cook (loop, propose-only) | Propose alternatives with trade-offs | `cheez-search` / `cheez-read` to validate approach claims; `Write` to `$TMPDIR/explore-<slug>-cook-c<N>.md` and (final cycle only) `$TMPDIR/explore-<slug>-approach.md` | Production-file edits; locking on a single approach without surfacing alternatives; skipping the "Do nothing" candidate |
| Cut | Decompose locked approach into failing tests | Test-file writes pinning each named obligation in the locked approach | Production-file edits; widening scope beyond the locked approach; reopening the approach decision |
| Cook (impl) | Implement against red tests | `cheez-write` on production files to turn Cut's red tests green; read-only Bash for build/test verification | Test-file edits (Cut owns red, Press owns post-impl); reopening the approach decision; folding rejected alternatives back in |
| Press | Adversarial post-impl | Boundary / chaos / integration test additions; run the test command and capture failures only | Production-file edits; build-config silencing; mutating git |
| Age | Review | The standard `age` skill six-dimension review, scoped to the locked approach's net diff | Re-opening the design conversation; widening scope beyond the locked approach |

## Execution protocol

The orchestrator runs the Culture↔Cook loop sequentially up to three
cycles, lands the approach lock, then walks the locked-approach pipeline
sequentially. Each stage hands off via its structured-summary contract
(defined on `agents/<stage>.md.eta`). The orchestrator works from
summaries; downstream stages read the prior stage's full report from
`$TMPDIR` only when they need deeper context.

Pick a kebab-case `<slug>` from the user's framing at step 1 and reuse
it across every $TMPDIR path for the run.

### Step 1 — classify, confirm, slug

1. Inspect `$ARGUMENTS`. Confirm it is exploration-shaped (fuzzy
   problem, no clear solution, no existing spec). Redirect:
   - **spec path or `<harness>/specs/...`** → `/fromage`.
   - **bug / stack trace / failing test / regression** → `/debug`.
   - **question with no intent to build** → `/culture`.
   - **feature description with a clear single approach** → `/mold`
     then `/fromage`.
   - **PR number or partially-done branch** → `/pr-finish`.
2. Derive a kebab-case `<slug>` from the framing (e.g.
   `cache-eviction-policy`, `oauth-refresh-flow`).
3. Announce the planned path — `Culture → Cook` loop with a three-cycle
   cap, then approach lock, then `Cut → Cook → Press → Age` — the slug,
   and the no-production-write invariant on every loop stage.
4. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow scope, or supply extra focusing context.
   Until confirm, no sub-agent runs.

### Step 2 — Culture↔Cook loop (cycle counter starts at 1)

Track `cycle_n` in the orchestrator context, starting at 1, capped at 3.
For each cycle, dispatch Culture then Cook. Culture is forbidden from
writing to production files (its source frontmatter disallows
`Edit`/`NotebookEdit`; the `Write` carve-out is `$TMPDIR` only). Cook
is dispatched in **propose-only mode** during the loop — its prompt
explicitly forbids production writes and constrains the Write target
to `$TMPDIR`.

#### Step 2a — Culture (cycle N)

```
Agent(
  subagent_type="culture",
  description="Explore <slug> — cycle <N> Culture pass",
  prompt="Exploration Flow (Flow 2) Culture cycle N=<cycle_n> for slug=<slug>.\n\n
Open question to ground:\n<verbatim $ARGUMENTS at cycle 1; Cook's surfaced focusing question at cycle 2+>\n\n
Deliverable: write the full Culture Report to $TMPDIR/explore-<slug>-culture-c<cycle_n>.md (override the default fromage-culture-<slug>.md path) and return the structured Culture Summary (max 2000 chars, per agents/culture.md.eta).\n\n
Required findings before Cook may run:\n
- Surface area (files, modules, public symbols touched by the question).\n
- Current behaviour and prior art links (commits, related specs).\n
- Constraints / invariants Cook must respect when proposing approaches.\n
- Open sub-questions — name them so Cook can decide whether to loop again."
)
```

#### Step 2b — Cook (cycle N, propose-only)

```
Agent(
  subagent_type="cook",
  description="Propose ≥2 approaches for <slug> — cycle <N>",
  prompt="Exploration Flow (Flow 2) Cook propose-only step for slug=<slug>, cycle N=<cycle_n>.\n\n
Read Culture's cycle report first: $TMPDIR/explore-<slug>-culture-c<cycle_n>.md.\n\n
Propose at least TWO candidate approaches PLUS a 'Do nothing' option. For each:\n
- Name (short, memorable).\n
- Scope and file impact.\n
- Risk and reversibility.\n
- Honest 'why not' against the others.\n\n
You are in propose-only mode — DO NOT EDIT production files this cycle. Write the proposal table to $TMPDIR/explore-<slug>-cook-c<cycle_n>.md and return the short Cook Summary (max 1500 chars, per agents/cook.md.eta) with status='propose-only' on every entry.\n\n
After the proposal, decide: (a) advance to approach lock if trade-offs are clear, or (b) loop back with one focusing question for Culture. State (a) or (b) explicitly in the summary; if (b), name the question."
)
```

#### Step 2c — branch decision

Inspect Cook's cycle summary.

- If Cook says `advance to lock` OR `cycle_n == 3` (cap reached) → exit
  the loop, fall through to Step 3 (approach lock). Cook's last cycle
  output IS the approach proposal.
- If Cook says `loop again` AND `cycle_n < 3` → increment `cycle_n` and
  return to Step 2a with Cook's surfaced focusing question as the next
  Culture prompt input.

### Step 3 — approach lock (the hard gate)

The orchestrator copies Cook's final cycle proposal into a clean
`$TMPDIR/explore-<slug>-approach.md` (so the file exists at a stable
path regardless of which cycle landed), then presents the proposal to
the user via `AskUserQuestion` with three choices:

1. **Lock approach N** → flow advances to Step 4 (Cut). The named
   approach becomes the locked plan.
2. **Loop again** → only available if `cycle_n < 3`; user supplies a
   focusing question and the flow returns to Step 2a with `cycle_n`
   incremented.
3. **Abort** → halt. Hand off to `/mold` (write the spec) or `/culture`
   (keep thinking) without entering Cut.

The proposal MUST include, before the user is asked to choose:

- Each candidate approach, named.
- Rejected alternatives with the one-line reason each was rejected.
- The file impact list Cut will use as its decomposition input.
- The Quality gates (commands that must pass for Age to clear).
- The unresolved questions (if any) Press must surface during execution.

No production file is touched until the lock fires. This is the
architectural backstop against the "agent never commits, costs escalate"
failure mode the Quintessential flow doc names for this flow.

### Step 4 — Cut (TDD contract definition for the locked approach)

Spawn the `cut` sub-agent against the locked approach to write red
tests pinning each named obligation. Cut is forbidden from writing to
production files (its source frontmatter disallows
`Edit`/`NotebookEdit`; its Permission Contract names tests-only writes).

```
Agent(
  subagent_type="cut",
  description="Write red tests for locked approach <approach name>",
  prompt="Exploration Flow (Flow 2) Cut step for slug=<slug>.\n\n
Read the locked approach first: $TMPDIR/explore-<slug>-approach.md.\n
Read Culture's most recent cycle report for surface context: $TMPDIR/explore-<slug>-culture-c<final_cycle>.md.\n\n
Deliverable: write the full Cut Report to $TMPDIR/fromage-cut-<slug>.md and return the structured Cut Summary (max 1500 chars, per agents/cut.md.eta).\n\n
Hard constraints:\n
- Pin only the obligations the locked approach *names* (file impact list + Quality gates). Do not invent edge cases — that is Press's job at step 6.\n
- One test per named happy path, one per named error contract, one per named boundary.\n
- Run the project's test command. Confirm every new test is **red** (fails on first run). If any pass without an implementation, the test is wrong — fix it before reporting.\n
- Per your Permission Contract you do not modify production code — that is Cook's job at step 5."
)
```

### Step 5 — Cook (implement against red tests)

Spawn the `cook` sub-agent in standard implementation mode (NOT
propose-only — the lock fired). Cook reads both the locked approach
and Cut's report so it knows the contract surface.

```
Agent(
  subagent_type="cook",
  description="Implement <approach name> against Cut's red tests",
  prompt="Exploration Flow (Flow 2) Cook impl step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/explore-<slug>-approach.md (locked approach + allowed-touch file list)\n
- $TMPDIR/fromage-cut-<slug>.md (Cut's red test inventory)\n\n
Implement the approach with cheez-write. Watch Cut's red tests turn green; capture only failures from the project's build/lint/test command.\n\n
Hard constraints:\n
- Edit only files the locked approach explicitly names. No 'while we're here' refactors.\n
- Per your Permission Contract you do not modify test files — that is Cut's pre-impl job and Press's post-impl job.\n
- The locked approach is now binding; do NOT fold rejected alternatives back in.\n
- Write your full Cook Report to $TMPDIR/fromage-cook-<slug>.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

### Step 6 — Press (adversarial post-implementation testing)

```
Agent(
  subagent_type="press",
  description="Adversarial post-impl tests for <approach name>",
  prompt="Exploration Flow (Flow 2) Press step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/explore-<slug>-approach.md (locked approach + production surface)\n
- $TMPDIR/fromage-cut-<slug>.md (contract pinned by Cut)\n
- $TMPDIR/fromage-cook-<slug>.md (what Cook changed)\n\n
Apply the testing priority order from your charter — invalid inputs, edge cases, integration paths, then happy path. Score every failure 0–100; surface findings >= 50 as critical. Pay special attention to the 'unresolved questions' section of the locked approach — those are Press's primary attack surface.\n\n
Per your Permission Contract you do not modify production code. If a failure suggests Cook's implementation is incomplete, surface it as a finding (>= 50) and let the orchestrator route the next iteration.\n\n
Write your full Press Report to $TMPDIR/fromage-press-<slug>.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

### Step 7 — Age (review, no-fix mode)

Invoke the `age` skill in `--no-fix` mode so the Explore orchestrator
stays in control of the fix loop.

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-plus-tests-touched-by-cut-and-press>"
)
```

The age skill writes its merged Age Report to `$TMPDIR/age-<slug>.md`
and returns a structured summary listing findings >= 50, verified
against the locked approach's Quality gates.

### Step 8 — fix loop, approach-invalidation halt, or success

Inspect the Age summary returned at step 7 plus the Press findings from
step 6.

- **No findings >= 50, Press is green, and the locked approach's
  Quality gates pass** → success. Surface the cumulative summary
  (chosen approach + Cut's contract count + Cook's diff stat + Press's
  robustness assessment + Age's "clean") and stop. The
  approach-lock proposal becomes the de-facto spec record (the user may
  promote it to `<harness>/specs/` via `/mold` if they want it
  versioned).
- **One or more findings >= 50 against the implementation only** → use
  `AskUserQuestion` to ask whether to continue the fix loop. On
  confirm, repeat **Step 5 (Cook)** scoped to the cited files only,
  then **Step 6 (Press)** and **Step 7 (Age)**. Re-running Cut for a
  fix-loop is wasteful — the contract was already pinned at step 4.
  Re-running Culture↔Cook would invalidate the lock and is forbidden
  here.
- **One or more findings >= 50 that challenge the locked approach
  itself** (Age finds the approach is internally inconsistent, Press
  uncovers a fundamental flaw the proposal missed, or a Quality gate
  collides with the chosen approach) → halt the flow. The locked-approach
  assumption is broken; surface the cumulative findings and recommend
  re-entering `/explore` with the new constraints, or `/mold` to
  formalize a different approach. Continuing the fix loop would compound
  the error.
- **Loop counter** — track impl-fix loop count starting at 1. After the
  **third** full Cook → Press → Age loop without convergence, halt and
  return cumulative findings. Further work needs human direction or a
  fresh `/explore` cycle.

## Stop conditions

`/explore` stops when **any** of the following is true:

- Age returns no findings >= 50, Press is green, and the locked
  approach's Quality gates pass → success.
- The user picks **Abort** at the approach lock → halt with the
  approach-lock proposal as a hand-off; no Cut work occurs.
- The Culture↔Cook loop hits the three-cycle cap with no convergent
  approach → halt and surface the alternatives on the table; recommend
  `/culture` or `/mold` for further exploration.
- A Cook → Press → Age fix attempt cycles more than **three** times
  without converging → halt and return cumulative findings.
- Age findings call the locked approach itself into question (not just
  the implementation) → halt; the approach lock is invalidated and the
  user is asked whether to re-enter `/explore` or `/mold`.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR`. The exact paths the agents use:

| Artifact | Full report path |
|---|---|
| Culture (cycle N) | `$TMPDIR/explore-<slug>-culture-c<N>.md` |
| Cook (cycle N, propose-only) | `$TMPDIR/explore-<slug>-cook-c<N>.md` |
| Approach lock proposal | `$TMPDIR/explore-<slug>-approach.md` |
| Cut | `$TMPDIR/fromage-cut-<slug>.md` |
| Cook (impl) | `$TMPDIR/fromage-cook-<slug>.md` |
| Press | `$TMPDIR/fromage-press-<slug>.md` |
| Age (skill) | `$TMPDIR/age-<slug>.md` |

The orchestrator overrides the default `fromage-culture-<slug>.md` /
`fromage-cook-<slug>.md` paths during the loop (cycle reports live in
the `explore-<slug>-*` namespace) and falls back to the canonical
`fromage-*` namespace for the post-lock pipeline. This keeps the loop
artifacts isolated from the impl artifacts and makes resume / debug
easier — a stale `explore-<slug>-approach.md` is the only state the
orchestrator must read to continue after a context loss.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)`, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the loop and post-lock stages are then
  expressed as sequential turns with the user supplying each handoff.
  The slug, $TMPDIR seam, approach-lock proposal, and report formats
  are unchanged — only the spawn mechanism degrades. Cycle counter
  must be tracked in the user's prompt header on each turn.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strict sequential handoff already matches that constraint.
- **Cursor** has no per-agent allowlist; the read-only invariant on
  Culture and the propose-only invariant on loop-Cook are enforced
  solely by prompt on Cursor (each agent's Permission Contract block
  is the backstop). Loop-Cook in particular is dispatched against the
  same `cook` agent that, after the lock, IS allowed to write
  production code — the propose-only constraint comes entirely from
  the Step 2b prompt.

In every harness, the four stage agents (`culture`, `cut`, `cook`,
`press`, plus the `age` skill) ARE the portable surface — the
Agent/Skill invocations are the Claude-flavored binding.

## Deferred behavior

The dispatch protocol above is now wired. Three enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Culture's no-production-write
  invariant and loop-Cook's propose-only invariant are currently
  enforced only by each agent's Permission Contract prompt and the
  source-frontmatter `disallowedTools` list. The compiler does not yet
  propagate `disallowedTools` / `permissionMode` into the rendered
  harness frontmatter, so on Claude Code these invariants are
  prompt-only at runtime.
- **Loop counter persistence** — the three-cycle cap on Culture↔Cook
  and the three-loop cap on Cook → Press → Age are enforced by the
  orchestrator tracking counters in-context. There is no durable
  counter file; if the Explore session is resumed in a fresh context,
  the caps reset. Persisting state under
  `$TMPDIR/explore-<slug>-state.json` would close this gap.
- **Loop-Cook propose-only mode** — the `cook` agent template has a
  single Permission Contract that allows production writes (its
  primary post-lock role). The propose-only constraint during the
  loop is layered on top via the Step 2b prompt. A first-class
  `cook --propose-only` flag in the source frontmatter (or a
  dedicated `cook-propose` agent) would make this enforceable
  rather than prompt-only.

All three gaps lower **Cross-cutting principle: Permission model per
stage** on the scoreboard, not Flow 2 itself.
