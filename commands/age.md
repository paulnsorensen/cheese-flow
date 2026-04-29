---
name: age
description: Review flow entry point. Routes nominally-complete code (PR, branch diff, module) through Culture (read-only diff + PR ingest) → Age (six-dimension review) → optional Cook fix-loop → Age (re-review), explicitly skipping Cut. Also reusable as the standalone review primitive inside other flows.
argument-hint: "[--comprehensive] [--scope <path>] [--no-fix] [<PR# | diff ref | branch | path>]"
---

# /age

`/age` is the entry point for the **Review Flow** (Flow 5 of the seven
canonical cheese-flow flows) and the standalone Staff Engineer review
primitive used by every other flow. The agent's role is critic, not
author: review sub-agents write findings, not fixes. The orchestrator
then either approves or spawns a bounded fix loop that re-enters Cook,
optionally Press for regression tests, then re-runs Age.

## Flow

The canonical Review flow in the design doc is `Culture → Age → loop`,
where the loop is `Press → Age (re-review)`. The cheese-flow agent
ecosystem maps those pipeline phases to TDD-flavored sub-agent roles
that resolve the canonical "Press is the fixer" framing:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Diff + PR + spec ingest | `culture` sub-agent | Read-only brief at $TMPDIR/age-<slug>-context.md |
| Six-dimension review | `age` skill | Spawns 6 dimension sub-agents in parallel, merges findings |
| Fix (production code) | `cook` sub-agent | Edits **only** files Age cited; production-code only |
| Fix (regression tests) | `press` sub-agent | Optional — adds tests for cleared findings; tests-only |
| Re-review | `age` skill (`--no-fix`) | Delta-only re-review on the fixed files |

So the **actual sub-agent dispatch order** is `Culture → age-skill → [Cook
(→ Press)? → age-skill] × up to 3`. The canonical "Press fixes, then Age
re-reviews" framing assumed Press was a generic fixer. Under agent
semantics, Cook is the primary fixer because most Age findings (bugs,
complexity, leaks, dead code, spec drift) are production-code issues that
press's tests-only Permission Contract forbids. Press is invoked only when
an Age finding explicitly demands a missing regression test.

```
Culture (ingest diff + PR + spec) → age skill (six dimensions in parallel)
                                        │
                            findings >= 50?
                              ├── no  → success
                              └── yes → Cook (fix prod) → Press (regression tests, optional) → age skill (re-review)
                                          (capped at three loops)
```

```
                      ┌──── Cut is skipped ─────┐
                      │                          │
Culture ──────────────┴────► Age ⇄ Cook (+ Press?)
```

Cut is **deliberately skipped**. The plan is encoded in the existing
diff or module; the question is whether it is good, not what new contract
to define. Inviting Cut back in widens scope — that is `/fromage` or
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
| Review-only | `--no-fix` | Suppress the Age→Cook fix loop; return findings and stop |

The `--no-fix` flag is the contract used when `/age` is invoked **as a
sub-step of another flow** (`/debug`, `/pr-finish`, `/fromage`,
`/incremental`, `/explore`). Those flows already own the fix loop; the
embedded `/age` call must surface findings and return without spawning
its own Cook cycle.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture (pre-pass) | Read-only ingest | `gh pr view`, `gh pr diff`, `gh pr checks`, `Bash(git log:*)`, `Bash(git diff:*)`, `cheez-search`, `cheez-read`, `briesearch`; `Write` only to `$TMPDIR/age-<slug>-context.md` | Any `Edit`, `Write` outside `$TMPDIR`, `NotebookEdit`, or git-mutating Bash on production files |
| Age skill (six dimensions) | Annotate-only critic | Per-dimension agent contracts: `cheez-search`, `cheez-read`, `Bash(git log:*)`, `Bash(git diff:*)`, `tilth_*` queries; `Write` only to `$TMPDIR/age-<slug>[-<dimension>].md` | Any `Edit`/`cheez-write` on production files; spawning fix sub-agents; rewriting tests; touching `.claude`, `.codex`, `.cursor`, `.copilot` |
| Cook (fix loop) | Bounded fixer | `cheez-write` on the files Age cited; full Bash for build/test; `gh` for status reads | Touching files Age did not cite; widening scope; new features; refactors unrelated to surfaced findings; rebasing or force-pushing without explicit user approval; editing tests (those go to Press) |
| Press (fix loop, optional) | Regression tester | `cheez-write` on test files only; full Bash for test execution | Editing production code; widening scope beyond the named missing-test finding; build-config or CI silencing |

The Culture and age-skill stages are **read-only on production files** by
contract. Cook (production fixes) and Press (regression tests) are the
only stages that may write to source / tests respectively. This is the
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

## Execution protocol

The orchestrator runs the stages sequentially. Each stage hands off via
its structured-summary contract (defined on `agents/<stage>.md.eta` and
`skills/age/SKILL.md`). The orchestrator works from summaries; downstream
stages read the prior stage's full report from `$TMPDIR` only when they
need deeper context.

Pick a kebab-case `<slug>` from the review target at step 1 and reuse it
across every $TMPDIR path for the run. For a PR the slug is `pr-<number>`;
for a branch it is the kebab branch name; for a path argument it is the
last path component.

### Step 1 — classify, derive slug, gate

1. Inspect `$ARGUMENTS`. Resolve to a concrete review target — accept
   `<PR#>`, `<branch>`, a diff ref (`HEAD~3..HEAD`), a path, or empty
   (= recent changes on the current branch). If none resolve, halt and
   ask.
2. Classify the input as review-shaped:
   - Bug report or failing CI → redirect to `/debug`.
   - Stalled PR with missing implementation work → redirect to `/pr-finish`.
   - Fresh feature with no code yet → redirect to `/mold` (spec) or
     `/fromage` (build).
   - Architectural exploration, no concrete diff → redirect to `/culture`
     (Learn) or `/explore`.
3. Derive a kebab-case `<slug>` per the rule above.
4. Announce the planned path — `Culture → age skill → [Cook (→ Press)?
   → age skill]?`, Cut skipped, Culture+age-skill read-only — and the
   slug. State whether the fix loop is enabled (default) or suppressed
   (`--no-fix`).
5. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow scope (`--scope`), or supply additional
   review context (linked spec, related PRs, focus areas).

### Step 2 — Culture pre-pass (read-only ingest)

Spawn the `culture` sub-agent in ingest mode. Culture is forbidden from
writing to production files (its source frontmatter disallows
`Edit`/`NotebookEdit`; the `Write` carve-out is `$TMPDIR` only).

```
Agent(
  subagent_type="culture",
  description="Ingest review context for <target>",
  prompt="Review Flow (Flow 5) Culture pre-pass for slug=<slug>.\n\n
Review target: <PR# / branch / diff ref / path from step 1>\n\n
Deliverable: write the full Culture brief to $TMPDIR/age-<slug>-context.md (override your default path so the brief is namespace-isolated from any concurrent /debug or /fromage Culture run on the same topic) and return the structured Culture Summary (max 2000 chars, per agents/culture.md.eta).\n\n
Required findings before age-skill may run:\n
- The PR number, branch, and base ref the diff is against.\n
- The PR description and any linked spec under <harness>/specs/<slug>.md (if any).\n
- The net diff surface (file list, change shape per file).\n
- Failing CI checks (`gh pr checks`) or open review threads, if any.\n
- Any prior Age reports for the same target (so a re-review knows what was already surfaced and what is newly introduced).\n
- Confidence (0-100) that the change is reviewable. If < 50 (no diff, no PR, no spec, contradictory commits), recommend `/pr-finish` or `/mold` and halt."
)
```

If Culture's confidence < 50 on reviewability, halt the flow at step 2.
Return Culture's recommendation (likely `/pr-finish` or `/mold`) and the
diagnostic summary; do not proceed to the age skill.

### Step 3 — Age skill (six-dimension parallel review)

Invoke the `age` skill, which spawns the six dimension sub-agents in
parallel and merges findings with history modifiers.

```
Skill(
  skill="age",
  args="--scope <files-from-culture-brief> [--comprehensive]"
)
```

The age skill reads Culture's brief from `$TMPDIR/age-<slug>-context.md`,
spawns the six dimensions (`age-safety`, `age-arch`, `age-encap`,
`age-yagni`, `age-spec`, `age-history`) in a single parallel-spawn
message, applies history-risk modifiers, and writes the merged report
to `$TMPDIR/age-<slug>.md`.

The structured Age Summary (max 2000 chars) returned to the orchestrator
lists findings >= 50 with their dimension, score, file:line anchor, and
suggested fix.

### Step 4 — fix-loop branch decision

Inspect the Age Summary returned at step 3.

- **No findings >= 50** → success path. Surface the cumulative summary
  (Culture's diff-surface line + age-skill's "clean" verdict +
  history-risk profile) and stop.
- **`--no-fix` set** → return the Age Report and stop, regardless of
  finding count. The caller (another flow) owns the fix decision.
- **Findings >= 50 and fix loop enabled** → proceed to step 5 with loop
  counter `loop = 1`.

For each fix iteration, use `AskUserQuestion` with three choices:
*confirm fix* (continue to step 5), *abort* (return findings only),
*spec-invalidation* (the findings call the design itself into question
— halt and recommend `/mold` or `/explore`).

### Step 5 — Cook (production-code fix)

Spawn the `cook` sub-agent scoped to the files Age cited.

```
Agent(
  subagent_type="cook",
  description="Apply Age-cited fixes for <target>",
  prompt="Review Flow (Flow 5) Cook fix step for slug=<slug>, loop=<N>.\n\n
Read both prior reports first:\n
- $TMPDIR/age-<slug>-context.md (Culture's diff surface + linked spec)\n
- $TMPDIR/age-<slug>.md (the six-dimension findings — only findings >= 50 are in scope)\n\n
Implement the smallest production change that clears the cited findings. Cut is skipped because this is a review fix loop, not a feature decomposition.\n\n
Hard constraints:\n
- Edit only files Age explicitly cited at score >= 50.\n
- No new features, no refactors, no 'while we're here' cleanups.\n
- Per your Permission Contract you do not modify test files — Press is dispatched separately at step 6 if any finding is `SPEC_MISSING` (regression test) shaped.\n
- No rebasing or force-pushing.\n
- Write your full Cook Report to $TMPDIR/fromage-cook-<slug>.md and return the short summary (max 1500 chars, per agents/cook.md.eta)."
)
```

If Cook returns `partial` or `skipped` for a finding, surface the blocker
and pause for user direction before continuing.

### Step 6 — Press (regression tests, optional)

If any age-skill finding was tagged `SPEC_MISSING` shaped (i.e. "missing
regression test for case X" rather than "fix bug X"), spawn the `press`
sub-agent to add the regression tests. Skip this step if every finding
was production-code only.

```
Agent(
  subagent_type="press",
  description="Add regression tests for Age-cited gaps in <target>",
  prompt="Review Flow (Flow 5) Press step for slug=<slug>, loop=<N>.\n\n
Read all three prior reports first:\n
- $TMPDIR/age-<slug>-context.md (Culture's diff surface)\n
- $TMPDIR/age-<slug>.md (Age findings — focus only on `SPEC_MISSING` shaped findings, score 0-100)\n
- $TMPDIR/fromage-cook-<slug>.md (what Cook just changed in this loop)\n\n
For each `SPEC_MISSING` finding, add a regression test that pins the missing case. Per your Permission Contract you do not edit production code.\n\n
Write your full Press Report to $TMPDIR/fromage-press-<slug>.md and return the short summary (max 1500 chars, per agents/press.md.eta)."
)
```

### Step 7 — re-review and convergence

Re-invoke the age skill in `--no-fix` mode for a delta-only re-review:

```
Skill(
  skill="age",
  args="--no-fix --scope <files-touched-by-cook-or-press-this-loop>"
)
```

Inspect the new Age Summary.

- **No findings >= 50** → success. Surface the cumulative delta (cleared
  / persisted / new findings per loop) and stop.
- **Findings >= 50 and `loop < 3`** → increment `loop` and return to
  step 4 (branch decision).
- **Findings >= 50 and `loop == 3`** → halt at the three-loop convergence
  cap. Return the cumulative findings; further work needs human direction
  or a fresh `/explore` / `/mold`.
- **Age findings call the spec or design itself into question** (not just
  the implementation) → halt regardless of loop count. The fix loop is
  invalidated; ask the user via `AskUserQuestion` whether to enter
  `/mold` (rewrite the spec) or `/explore` (rethink the approach).

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
- The Cook (→ Press) → Age fix loop runs more than **three** times
  without converging → halt and return cumulative findings.
- Age findings call the spec or design itself into question → halt; the
  fix loop is invalidated and the user is asked whether to enter `/mold`
  or `/explore`.

## Hand-off contract

Each stage returns a compact summary to the orchestrator (per the
agent-level summary contracts) and writes its full report to
`$TMPDIR`. The exact paths the agents use:

| Stage | Full report path |
|---|---|
| Culture (pre-pass) | `$TMPDIR/age-<slug>-context.md` (override of Culture's default `fromage-culture-<slug>.md`) |
| Age skill (initial) | `$TMPDIR/age-<slug>.md` |
| Cook (fix loop, per loop N) | `$TMPDIR/fromage-cook-<slug>.md` (overwritten each loop — the canonical Cook seam is single-shot per slug) |
| Press (fix loop, per loop N) | `$TMPDIR/fromage-press-<slug>.md` (overwritten each loop, same reasoning) |
| Age skill (re-review, per loop N) | `$TMPDIR/age-<slug>-loop-<N>.md` |

The `age-<slug>-context.md` path is intentionally distinct from the
canonical `fromage-culture-<slug>.md` Culture seam so an embedded `/age`
call inside `/debug` or `/fromage` does not clobber the parent flow's
Culture brief.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)`, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the stages are then expressed as
  sequential turns with the user supplying each handoff. The slug,
  $TMPDIR seam, and report formats are unchanged — only the spawn
  mechanism degrades. The age skill itself is a SKILL (not an agent)
  and runs inline in the caller's context, so its parallel-six-dimension
  spawn collapses to sequential per-dimension turns on Codex.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  Culture → age-skill → Cook → Press → age-skill outer sequence already
  matches that constraint. The age skill's six-dimension parallelism
  becomes sequential on Copilot — total wall time grows but the merged
  report is unchanged.
- **Cursor** has no per-agent allowlist; the read-only invariant on
  Culture and the six dimension agents is enforced solely by prompt on
  Cursor (each agent's Permission Contract block is the backstop).

In every harness, the Culture sub-agent + the age skill (which embeds
the six dimension agents) + the Cook and Press sub-agents ARE the
portable surface — the Agent/Skill invocations are the Claude-flavored
binding.

## Deferred behavior

The dispatch protocol above is now wired. Three enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Culture's no-production-write
  invariant is currently enforced only by the agent's Permission Contract
  prompt and the source-frontmatter `disallowedTools` list. The compiler
  does not yet propagate `disallowedTools` / `permissionMode` into the
  rendered harness frontmatter, so on Claude Code the invariant is
  currently prompt-only at runtime.
- **Loop counter persistence** — the three-loop cap is enforced by the
  orchestrator tracking loop count in-context. There is no durable
  counter file; if the Review session is resumed in a fresh context the
  cap resets. Persisting loop state under
  `$TMPDIR/age-<slug>-state.json` would close this gap.
- **Finding-shape classifier** — the step-6 Press dispatch hinges on
  classifying which Age findings are `SPEC_MISSING` shaped vs production
  bug shaped. The age skill's category vocabulary already includes
  `SPEC_MISSING`, but the classification is currently delegated to the
  orchestrator's prompt parsing. A first-class `--classify` flag on the
  age skill that returns `production_fix` / `regression_test_only`
  buckets would close this.

All three gaps lower **Cross-cutting principle: Permission model per
stage** and **Stop conditions per phase** on the scoreboard, not Flow 5
itself.
