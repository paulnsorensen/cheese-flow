---
name: pr-finish
description: PR-Finish flow entry point. Routes a partially-done branch (WIP, stalled PR, missing tests, post-rebase fallout) through Culture (read diff + PR context) → Cut (pin remaining contract as red tests) → Cook (execute) → Press (adversarial post-impl) → Age (review). The canonical-doc Cook-skip means "no fresh planning"; under the agent ecosystem the cook sub-agent still owns execution.
argument-hint: "<PR# | branch name | diff ref | path to WIP description>"
---

# /pr-finish

`/pr-finish` is the entry point for the **PR-Finish / Continuation Flow**
(Flow 4 of the seven canonical cheese-flow flows). Use it when a branch
already contains in-progress work and you want the agent to complete,
extend, or clean it up before merge.

## Flow

The canonical PR-Finish flow in the design doc is `Culture → Cut → Press →
Age` (Cook skipped), where the stage names refer to *pipeline phases*
(read context → decompose remaining → execute → review). The cheese-flow
agent ecosystem has assigned TDD-flavored roles to those names:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Read PR + diff + CI + comments | `culture` sub-agent | Diff ingest, failing-checks read, open-thread harvest |
| Decompose remaining (define contract) | `cut` sub-agent | Write failing tests pinning each remaining obligation the PR named |
| Execute | `cook` sub-agent | Production code that turns Cut's red tests green and closes CI failures |
| Adversarial verify | `press` sub-agent | Post-impl boundary / chaos / integration tests |
| Review | `age` skill | Six-dimension merged review, scoped to net diff (base..HEAD) |

So the **actual sub-agent dispatch order is `Culture → Cut → Cook → Press →
Age`**. The canonical-doc "Cook skipped" means there is **no fresh
architectural Cook phase** — the architectural decision is encoded in the
existing PR description, prior commits, and any linked spec. The `cook`
sub-agent is still dispatched at step 4 to do the actual remaining
implementation work; it just runs against a plan derived from the PR, not
against a fresh spec.

If Culture concludes the existing work is too divergent or under-specified
to finish (no PR description, no spec link, contradictory commits), the
flow halts and redirects to `/mold` instead of forcing a planning Cook
phase in. Re-cooking from scratch would discard the existing direction
and invent a new spec; that is `/mold` + `/fromage` territory, not
PR-Finish.

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Start a coherent feature from a fresh spec | `/fromage` |
| Discover the approach (no spec yet) | `/explore` |
| Walk an N-task backlog one at a time | `/incremental` |
| Decompose a large spec into parallel worktree atoms | `/fromagerie` |
| Fix a specific bug | `/debug` |
| Just review existing code | `/age` |
| Write a spec and stop | `/mold` |

`/pr-finish` is for **one branch with in-flight work, sequential
continuation, single Age gate at the end, approval gate between Cut and
Cook** (the only flow where the human-in-the-loop sits *inside* the
dispatch chain rather than at flow entry).

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Plan derivation (orchestrator) | Resolve PR + light grounding | `gh pr view`, `gh pr diff`, `gh pr checks`, `Bash(git log:*)`, `Bash(git diff:*)`; `Write` to `$TMPDIR/pr-finish-<slug>-plan.md` | Mutating git (commits, rebase, push); production-file edits; renegotiating the PR's stated goal |
| Culture | Read-only ingest | `cheez-search`, `cheez-read`, `briesearch`, `Bash(git log:*)`, `Bash(git diff:*)`; `Write` to `$TMPDIR/fromage-culture-<slug>.md` | Any `Edit`, `Write` outside `$TMPDIR`, `NotebookEdit`, or git-mutating Bash |
| Cut | TDD red-tests for remaining obligations | Write failing tests under `tests/` pinning each remaining obligation Culture surfaced; run the test command to confirm red | Production-file edits; inventing edge cases the PR did not name (that's Press post-impl); commits |
| Cook | Implement against the red tests | `cheez-write` on production files to turn Cut's red tests green; read-only Bash for build/test verification | Test-file edits (Cut owns red, Press owns post-impl); build-config silencing; mutating git; touching files outside Culture's surface |
| Press | Adversarial post-impl | Boundary / chaos / integration test additions under `tests/`; run the test command and capture failures only | Production-file edits; build-config silencing; mutating git |
| Age | Review | The standard `age` skill six-dimension review, scoped to the PR's net diff (base..HEAD) | Re-opening the design conversation; widening scope beyond the PR |

## Approval gate (between Cut and Cook)

The defining constraint of this flow: **Cut surfaces the remaining-work
contract as red tests + a structured task list and pauses for human
approval before Cook touches any production file.** This is the only flow
where the human-in-the-loop gate is between Cut and Cook rather than at
flow entry. The reason: the human already opened the PR and signalled
intent; the open question is whether the remaining-work decomposition
matches their expectation. The canonical-doc places this gate "between
Cut and Press" because under pipeline-phase semantics Press is the
executor; under agent semantics the executor is `cook`, so the gate
shifts one stage to the right.

## Execution protocol

The orchestrator runs the stages sequentially. Each stage hands off via
its structured-summary contract (defined on `agents/<stage>.md.eta`).
The orchestrator works from summaries; downstream stages read the prior
stage's full report from `$TMPDIR` only when they need deeper context.

Pick a kebab-case `<slug>` from the PR number or branch name at step 1
and reuse it across every $TMPDIR path for the run.

### Step 1 — resolve, classify, confirm

1. **Resolve `$ARGUMENTS`** to a concrete branch + PR. Accept `<PR#>`,
   `<branch>`, a diff ref (`HEAD~3..HEAD`), or a path to a WIP
   description. If none resolve, halt and ask for a PR or branch.
2. **Classify the input as continuation-shaped.** If the PR has no
   commits or no description and the user is actually starting from
   scratch, redirect to `/mold` or `/cheese`. If the PR is fully done
   and the user just wants review, redirect to `/age`.
3. **Derive a kebab-case `<slug>`** — `pr-<number>` for a PR
   (e.g. `pr-1234`) or the kebab-cased branch name (e.g.
   `feat-rate-limiter`). Reuse it for every $TMPDIR path below.
4. **Write a stub plan** to `$TMPDIR/pr-finish-<slug>-plan.md` with the
   PR number / branch, the PR's stated goal (verbatim from the
   description), and the failing-checks list (from `gh pr checks`). The
   plan stays a stub until Culture fills in the diff surface at step 2.
5. **Announce** the planned path — `Culture → Cut → Cook → Press → Age`,
   approval gate between Cut and Cook, Culture is read-only — and the
   slug.
6. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect or supply additional context (linked spec, related
   PRs, CI failure links) before Culture begins.

### Step 2 — Culture (read-only PR + diff ingest)

Spawn the `culture` sub-agent in PR-ingest mode. Culture is forbidden
from writing to production files (its source frontmatter disallows
`Edit`/`NotebookEdit`; the `Write` carve-out is `$TMPDIR` only).

```
Agent(
  subagent_type="culture",
  description="Ingest PR <slug> diff and context",
  prompt="PR-Finish Flow (Flow 4) Culture pre-pass for slug=<slug>.\n\n
PR / branch under continuation:\n<PR# or branch + URL>\n\n
Read the orchestrator stub plan at $TMPDIR/pr-finish-<slug>-plan.md to confirm goal + failing-checks list, then enrich it. Required deliverables:\n
- The PR's stated goal (verbatim or paraphrased; flag if missing).\n
- The current diff surface — list every file touched in base..HEAD with a one-line description.\n
- Failing CI checks (from `gh pr checks`) with the failure summary line for each.\n
- Open review threads on the PR with a one-line stance per thread.\n
- Linked specs (from PR body links, commit messages, or `.claude/specs/`) with the relevant section reference.\n
- A divergence assessment: is the existing work coherent enough to finish (confidence 0-100)? If < 50, recommend `/mold` and stop.\n\n
Deliverable: write the full Culture Report to $TMPDIR/fromage-culture-<slug>.md and return the structured Culture Summary (max 2000 chars, per agents/culture.md.eta)."
)
```

If Culture's divergence-assessment confidence < 50, halt the flow.
Surface the diagnostic to the user and recommend `/mold`; do not proceed
to Cut.

### Step 3 — Cut (TDD contract for remaining obligations) + approval gate

Spawn the `cut` sub-agent against Culture's surface to pin every
remaining PR obligation as a red test. Cut is forbidden from writing
to production files (its source frontmatter disallows `Edit`; its
Permission Contract names tests-only writes).

```
Agent(
  subagent_type="cut",
  description="Pin remaining contract for PR <slug> as red tests",
  prompt="PR-Finish Flow (Flow 4) Cut step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/pr-finish-<slug>-plan.md (PR goal + failing-checks list)\n
- $TMPDIR/fromage-culture-<slug>.md (diff surface, open threads, linked spec sections)\n\n
Deliverable: write the full Cut Report to $TMPDIR/fromage-cut-<slug>.md and return the structured Cut Summary (max 1500 chars, per agents/cut.md.eta).\n\n
Hard constraints:\n
- Pin only obligations the PR / linked spec / open review threads *named*. Do not invent edge cases — that is Press's job at step 5.\n
- Each failing CI check is a contract claim; write at least one test that captures the failure mode the check enforces (or assert the missing behavior the check expects).\n
- One test per named happy path, one per named error contract, one per named boundary. Names follow `subject_scenario_expectedBehavior`.\n
- Run the project's test command. Confirm every new test is **red**. If any pass without an implementation, the test is wrong — fix it before reporting.\n
- Per your Permission Contract you do not modify production code — that is Cook's job at step 4."
)
```

After Cut returns, **fire the approval gate**:

1. Surface inline: the PR / branch under continuation, Cut's task list
   (numbered, with file targets, scored against PR goal coverage), the
   merge-readiness checklist Cook + Press will run before declaring done
   (build green, CI checks green, no merge conflicts with base).
2. Use `AskUserQuestion` with three choices: **confirm** (proceed to
   Cook), **edit** (return Cut's task list for the user to revise; do
   not proceed), **abort** (halt the flow).
3. On **confirm**, continue to step 4. On **edit** or **abort**, do not
   spawn `cook`.

### Step 4 — Cook (execute against red tests)

Spawn the `cook` sub-agent to turn Cut's red tests green. Cook reads
Culture's full report and Cut's report so it knows the diff surface
and the contract.

```
Agent(
  subagent_type="cook",
  description="Finish PR <slug> by turning Cut's red tests green",
  prompt="PR-Finish Flow (Flow 4) Cook step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/pr-finish-<slug>-plan.md (PR goal + failing-checks list)\n
- $TMPDIR/fromage-culture-<slug>.md (diff surface — the only files you may modify)\n
- $TMPDIR/fromage-cut-<slug>.md (red test inventory — your contract)\n\n
Implement the smallest production change that turns every red test green and closes the failing CI checks. Watch the test command output; capture only failures.\n\n
Hard constraints:\n
- Edit only files Culture's diff surface enumerates — no widening scope, no 'while we're here' refactors.\n
- Per your Permission Contract you do not modify test files — that is Cut's pre-impl job and Press's post-impl job.\n
- No new features beyond the PR's stated goal; no goals added; no original commits reverted.\n
- Do not rebase, force-push, or run any mutating git operation; the orchestrator owns history.\n
- Write your full Cook Report to $TMPDIR/fromage-cook-<slug>.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

If Cook returns `partial` or `skipped` for a relevant plan step,
surface the blocker and pause for user direction before continuing.

### Step 5 — Press (adversarial post-implementation testing)

Spawn the `press` sub-agent to attack the now-green implementation
with the edge cases the PR did not name — boundary / chaos /
integration failure modes — scored 0–100.

```
Agent(
  subagent_type="press",
  description="Adversarial post-impl tests for PR <slug>",
  prompt="PR-Finish Flow (Flow 4) Press step for slug=<slug>.\n\n
Read prior artifacts first:\n
- $TMPDIR/pr-finish-<slug>-plan.md (PR goal)\n
- $TMPDIR/fromage-culture-<slug>.md (diff surface)\n
- $TMPDIR/fromage-cut-<slug>.md (contract pinned by Cut)\n
- $TMPDIR/fromage-cook-<slug>.md (what Cook changed)\n\n
Apply the testing priority order from your charter — invalid inputs, edge cases, integration paths, then happy path. Score every failure 0–100; surface findings >= 50 as critical.\n\n
Per your Permission Contract you do not modify production code. If a failure suggests Cook's implementation is incomplete, surface it as a finding (>= 50) and let the orchestrator route the next iteration.\n\n
Write your full Press Report to $TMPDIR/fromage-press-<slug>.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

### Step 6 — Age (review, no-fix mode)

Invoke the `age` skill in `--no-fix` mode so the PR-Finish orchestrator
stays in control of the fix loop. `/age` would otherwise prompt for
its own Press cycle and double-spawn it.

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-plus-tests-touched-by-cut-and-press>"
)
```

The age skill writes its merged Age Report to `$TMPDIR/age-<slug>.md`
and returns a structured summary listing findings >= 50, scoped to the
PR's net diff (base..HEAD).

### Step 7 — fix loop, divergent-PR halt, or success

Inspect the Age summary returned at step 6 plus the Press findings from
step 5 plus `gh pr checks` on the PR.

- **No findings >= 50, Press is green, and CI checks on the PR are
  green** → success. Surface the cumulative summary (Culture's
  divergence assessment + Cut's contract count + Cook's diff stat +
  Press's robustness assessment + Age's "clean") and stop. The
  orchestrator does NOT push or merge — that is the user's call.
- **One or more findings >= 50 against the implementation only** → use
  `AskUserQuestion` to ask the user whether to continue the fix loop.
  On confirm, repeat **Step 4 (Cook)** scoped to the cited files only,
  then **Step 5 (Press)** and **Step 6 (Age)**. Re-running Culture or
  Cut for a fix-loop is wasteful — the diff surface and the contract
  were pinned at steps 2-3.
- **One or more findings >= 50 that challenge the PR's stated goal**
  (Age finds the goal contradicts a quality gate, the linked spec
  diverges from the diff, or open review threads are unresolvable
  inside the PR scope) → halt the flow and recommend `/mold` to revise
  the spec. The continuation assumption of this flow is broken;
  continuing would compound the error.
- **Loop counter** — track loop count starting at 1. After the **third**
  full Cook → Press → Age loop without convergence, halt and return
  cumulative findings. Further work needs human direction or a fresh
  `/mold` to revise the spec.

## Stop conditions

`/pr-finish` stops when **any** of the following is true:

- Age returns no findings >= 50, Press is green, and CI checks on the
  PR are green → success.
- Culture concludes the PR is too divergent / under-specified to finish
  (confidence < 50 that this is a continuation problem) → halt and
  recommend `/mold`. No `cut` / `cook` / `press` spawn.
- The user rejects Cut's task list at the approval gate → halt and
  return the task list for editing; no Cook work occurs.
- A fix attempt cycles through Cook → Press → Age more than **three**
  times without converging → halt and return cumulative findings.
  Further work needs human direction or a fresh `/mold`.
- Age findings call the PR's stated goal into question (not just the
  implementation) → halt; the goal is invalidated and the user is
  asked whether to re-enter `/mold` or abort.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR`. The exact paths the agents use:

| Artifact | Full report path |
|---|---|
| Plan stub (orchestrator) | `$TMPDIR/pr-finish-<slug>-plan.md` |
| Culture | `$TMPDIR/fromage-culture-<slug>.md` |
| Cut | `$TMPDIR/fromage-cut-<slug>.md` |
| Cook | `$TMPDIR/fromage-cook-<slug>.md` |
| Press | `$TMPDIR/fromage-press-<slug>.md` |
| Age (skill) | `$TMPDIR/age-<slug>.md` |

The orchestrator works from the short summaries; downstream stages read
the prior stage's full report from `$TMPDIR` only when they need deeper
context. This keeps the orchestrator's window small across the five
stages even through three Cook → Press → Age fix loops.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)`, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the five stages are then expressed as
  sequential turns with the user supplying each handoff. The slug,
  $TMPDIR seam, plan stub, and report formats are unchanged — only the
  spawn mechanism degrades.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strict sequential handoff already matches that constraint.
  The `gh pr` / GitHub-Agentic-Workflows trigger surface is already
  Copilot-native, so this flow translates well.
- **Cursor** has no per-agent allowlist; the read-only invariant on
  Culture and the no-production-write invariants on Cut and Press are
  enforced solely by prompt on Cursor (each agent's Permission Contract
  block is the backstop).

In every harness, the five stage agents (`culture`, `cut`, `cook`,
`press`, plus the `age` skill) ARE the portable surface — the
Agent/Skill invocations are the Claude-flavored binding.

## Deferred behavior

The dispatch protocol above is now wired. Two enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Culture's no-production-write
  invariant and Cut/Press's tests-only invariants are currently enforced
  only by each agent's Permission Contract prompt and the
  source-frontmatter `disallowedTools` list. The compiler does not yet
  propagate `disallowedTools` / `permissionMode` into the rendered
  harness frontmatter, so on Claude Code the invariants are currently
  prompt-only at runtime.
- **Loop counter persistence** — the three-loop cap is enforced by the
  orchestrator tracking loop count in-context. There is no durable
  counter file; if the PR-Finish session is resumed in a fresh context
  the cap resets. Persisting loop state under
  `$TMPDIR/pr-finish-<slug>-state.json` would close this gap.

Both gaps lower **Cross-cutting principle: Permission model per stage**
on the scoreboard, not Flow 4 itself.
