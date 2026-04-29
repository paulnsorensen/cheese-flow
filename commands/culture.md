---
name: culture
description: Learn flow entry point. Routes a question or half-formed idea through a single read-only Culture deep-dive (no Cook, no Cut, no Press, no Age). The goal is a shared mental model, not code, spec, or PR output.
argument-hint: "<question | half-formed idea | onboarding topic | architectural curiosity>"
---

# /culture

`/culture` is the entry point for the **Learn Flow** (Flow 7 of the seven
canonical cheese-flow flows). Use it to rubber-duck a design, walk through
an unfamiliar part of the codebase, or talk out an ambiguous problem before
deciding what to actually build.

This is the only flow whose path is a single stage. Every other flow ends
in Press + Age and produces a diff; Learn ends in a structured summary and
produces understanding.

## Flow

The canonical Learn flow in the design doc is `Culture (only)` — or
optionally `Culture → Cook (draft explanation)`. The cheese-flow agent
ecosystem maps those pipeline phases as follows:

| Pipeline phase | Agent that performs it | Role |
|---|---|---|
| Discover | `culture` sub-agent | Read-only deep-dive scoped to the user's question, written to `$TMPDIR` |
| Draft explanation (canonical "Cook") | NOT dispatched | The production-code-only Cook contract is incompatible with docs-only output; the orchestrator aggregates Culture's report into the learn summary instead |
| Cut / Press / Age | NOT dispatched | Learn flow does not decompose, build, test, or review |

So the **actual sub-agent dispatch order** is `Culture` — once per cycle,
up to three cycles total. No production code is ever written; no test
file is ever written; no commit is ever made.

```
Culture (read-only deep-dive)
    │
    ├─► [understanding sufficient] → return structured learn summary
    ├─► [need another aspect] → loop Culture (cap = 3 cycles)
    └─► [discovery: should build / spec / fix] → halt + redirect to
        /explore | /mold | /debug | /fromage | /pr-finish | /briesearch
```

## Hard invariant: no writes to production

`/culture` **never writes to production files.** No code changes, no
spec file, no PR, no commits. The only filesystem writes permitted in
the entire flow are:

- The `culture` sub-agent's report under `$TMPDIR/fromage-culture-<slug>.md`
  (and `$TMPDIR/learn-<slug>-culture-c<N>.md` for cycles 2-3).
- The orchestrator's aggregated learn summary under
  `$TMPDIR/learn-<slug>-summary.md`.

Nothing under the repo root is touched. If the dialogue discovers that
something concrete should be built, specced, or fixed, `/culture` halts
and recommends the correct next flow — it does not cross the line itself.

## Distinguish from sibling flows

| If you want to… | Use instead |
|---|---|
| Discover an approach AND build it | `/explore` |
| Write a spec to a file (no execution) | `/mold` |
| Build a known spec end-to-end | `/fromage` (or `/fromagerie` for parallel atoms) |
| Walk an existing backlog of tasks | `/incremental` |
| Continue a partially-done PR | `/pr-finish` |
| Fix a bug | `/debug` |
| Look up an external library or API | `/briesearch` |
| Review existing code | `/age` |

`/culture` is the bridge between curiosity and commitment. The mental
model is the **only** byproduct. If you want anything written to disk
under the repo root, you are in the wrong flow — pick from the table.

## Stage contract

| Stage | Mode | Allowed | Forbidden |
|---|---|---|---|
| Culture (per cycle) | Read-only deep-dive | `cheez-search`, `cheez-read`, `briesearch`, `Bash(git log:*)`, `Bash(git diff:*)`, `Bash(ls:*)`, `Write` to `$TMPDIR/learn-<slug>-culture-c<N>.md` | Any production-file `Edit` / `Write` / `NotebookEdit`; any test-file write; mutating git Bash; spawning sub-agents |

There is no other stage row because no other agent runs.

## Execution protocol

The orchestrator runs Culture sequentially, capped at three cycles. Each
cycle hands off via Culture's structured-summary contract (defined on
`agents/culture.md.eta`). The orchestrator works from summaries; only
reads each cycle's full report from `$TMPDIR` when composing the final
learn summary.

Pick a kebab-case `<slug>` from the user's question at step 1 and reuse
it across every $TMPDIR path for the run.

### Step 1 — classify, redirect, slug, confirm

1. Inspect `$ARGUMENTS`. Confirm it is Learn-shaped (a question, a
   half-formed idea, an onboarding topic, an architectural curiosity,
   a "how does X work" or "what would change if Y" framing). Redirect:
   - **bug / stack trace / failing test / regression** → `/debug`.
   - **fuzzy problem with intent to build once an approach is found** →
     `/explore`.
   - **feature description with a clear single approach** → `/mold`
     then `/fromage`.
   - **spec path or existing `<harness>/specs/...`** → `/fromage`.
   - **PR number or partially-done branch** → `/pr-finish`.
   - **external library / API / framework reference question** →
     `/briesearch`.
   - **review existing code for issues** → `/age`.
2. Derive a kebab-case `<slug>` from the question (e.g.
   `how-mcp-proxy-routes-tool-calls`, `compiler-frontmatter-shape`,
   `sliced-bread-crust-rule`).
3. Announce the planned path — `Culture (only)`, read-only — the slug,
   and the no-production-write invariant.
4. Use `AskUserQuestion` to gate-check before any sub-agent spawns. The
   user may redirect, narrow scope, or supply extra focusing context.
   Until confirm, no sub-agent runs.

### Step 2 — Culture deep-dive (cycle counter starts at 1)

Track `cycle_n` in the orchestrator context, starting at 1, capped at 3.
For each cycle, dispatch a single `culture` sub-agent. Culture is
forbidden from writing to production files (its source frontmatter
disallows `Edit`/`NotebookEdit`; the `Write` carve-out is `$TMPDIR`
only).

```
Agent(
  subagent_type="culture",
  description="Learn <slug> — cycle <N> deep-dive",
  prompt="Learn Flow (Flow 7) Culture deep-dive for slug=<slug>, cycle N=<cycle_n>.\n\n
Question / topic to ground:\n<verbatim $ARGUMENTS at cycle 1; user's focusing question at cycle 2-3>\n\n
Mode: deep understanding for a human reader, not problem diagnosis. The user wants a mental model, not a fix or a plan. There is no downstream Cook / Cut / Press / Age — your report IS the deliverable.\n\n
Deliverable: write the full Culture Report to $TMPDIR/learn-<slug>-culture-c<cycle_n>.md (override the default fromage-culture-<slug>.md path so the Learn flow's per-cycle artifacts are namespace-isolated) and return the structured Culture Summary (max 2000 chars, per agents/culture.md.eta).\n\n
Required findings:\n
- 3-7 essential entry points / key files for the topic (file:line — one-line description each).\n
- The execution flow / data transformations that explain the topic.\n
- The architectural pattern(s) the user should internalize (e.g. 'Sliced Bread crust', 'TDD red→green', 'compaction seam').\n
- One paragraph: 'if you understand this, you can answer X / build Y / debug Z'.\n
- Open sub-questions that would warrant another Culture cycle (the user decides at Step 3 whether to loop).\n\n
Per your Permission Contract: do NOT modify any production or test file. Do NOT spawn sub-agents. The only Write target is the $TMPDIR cycle report path above."
)
```

If Culture's summary is empty or signals confidence < 50 on the topic
(no entry points found, no executable mental model formed), surface
that to the user at Step 3 and offer to redirect to `/briesearch`
(if the topic is library-shaped) or `/explore` (if the topic is
problem-shaped that needs an approach decision before deep-diving).

### Step 3 — orchestrator-side learn summary + branch decision

Read the Culture report(s) for every completed cycle from `$TMPDIR`.
Compose an aggregated learn summary at
`$TMPDIR/learn-<slug>-summary.md` with this shape:

```
## Learn Summary: <user's question>

### Essential files (3-7)
- <path>:<line> — <why it matters>

### What to internalize
<one paragraph from each cycle's "what to internalize", merged>

### Open sub-questions
<bulleted list of unresolved aspects, if any>

### Cycles run
<N> of 3
```

Then use `AskUserQuestion` with three choices:

1. **Understanding sufficient** → exit at Step 4 with the learn summary.
2. **Need another aspect** → only available if `cycle_n < 3`. The user
   supplies a focusing question; increment `cycle_n` and return to
   Step 2 with that question as the Culture prompt input.
3. **Discovery: should build / spec / fix something** → halt and
   recommend the appropriate next flow:
   - "Want to discover an approach AND build it" → `/explore`
   - "Want to write a spec to a file" → `/mold`
   - "Want to build a known spec end-to-end" → `/fromage`
   - "Want to fix a bug" → `/debug`
   - "Want to continue a partial PR" → `/pr-finish`

### Step 4 — exit

Return the structured learn summary to the user as the canonical
artifact for the session. Cite the `$TMPDIR/learn-<slug>-summary.md`
path so the user can fetch the durable copy if they want to paste it
elsewhere. NEVER write to production. NEVER spawn cook / cut / press /
age. NEVER recommend `/culture` recursively — if the user wants more
depth, that's branch (2) "another aspect" inside Step 3, not a fresh
session.

## Stop conditions

`/culture` stops when **any** of the following is true:

- User selects "understanding sufficient" at Step 3 → success.
- Three Culture cycles complete without the user signaling enough →
  halt cleanly, return the cumulative learn summary, and recommend
  `/explore` or `/mold` if the user wants to keep going beyond the cap.
- User redirects at Step 1 or selects "discovery → halt" at Step 3 →
  surface the recommended next command and exit cleanly.
- Culture returns an empty or low-confidence summary at any cycle →
  surface to the user at Step 3 and offer the redirect menu (no
  silent retry).

## Hand-off contract

Each Culture cycle returns a compact summary to the orchestrator (per
`agents/culture.md.eta`) and writes its full report to `$TMPDIR`. The
exact paths:

| Stage | Full report path | Visibility |
|---|---|---|
| Culture cycle 1 | `$TMPDIR/learn-<slug>-culture-c1.md` | Persisted across cycles |
| Culture cycle 2 | `$TMPDIR/learn-<slug>-culture-c2.md` | Persisted across cycles |
| Culture cycle 3 | `$TMPDIR/learn-<slug>-culture-c3.md` | Persisted across cycles |
| Orchestrator learn summary | `$TMPDIR/learn-<slug>-summary.md` | Returned to user as the canonical artifact |

Note the namespace separation: Learn-flow Culture reports use the
`learn-<slug>-culture-c<N>.md` path (passed to the agent prompt as an
override), distinct from the canonical `fromage-culture-<slug>.md` path
the agent defaults to. This keeps Learn-flow per-cycle artifacts
isolated from any concurrent `/explore` or `/debug` run on the same
topic that might also use slug-style naming.

The orchestrator works from the short summaries. Reading the full
cycle reports is deferred to Step 3 (when composing the aggregated
learn summary) so the orchestrator's window stays small across all
three cycles.

## Cross-harness portability

The protocol is written in the canonical Claude Code vocabulary
(`Agent(subagent_type=...)`, `Skill(...)` is unused, `AskUserQuestion`).

- **Codex** has no `Agent` tool; the three Culture cycles collapse into
  three sequential Codex turns directed by the Step 2 prompt. The slug,
  $TMPDIR seam, and report formats are unchanged — only the spawn
  mechanism degrades. The cycle counter degrades to user-tracked.
- **Copilot CLI** has agent metadata but no parallel-spawn tool; the
  protocol's strictly-sequential cycle handoff already matches that
  constraint. Fully native.
- **Cursor** has no per-agent allowlist; the no-production-writes
  invariant on Culture is enforced solely by the `culture` agent's
  Permission Contract block (its source frontmatter `disallowedTools`
  is dropped at compile time on Cursor).

In every harness, the `culture` sub-agent IS the portable surface — it
is the only agent the Learn flow ever dispatches. The `Agent` and
`AskUserQuestion` invocations are the Claude-flavored binding around
that surface.

## Deferred behavior

The dispatch protocol above is now wired. Two enforcement gaps remain
and are blocked on TS source changes (out of scope for this loop):

- **Tool-layer permission enforcement** — Culture's no-production-write
  invariant is currently enforced only by the agent's Permission
  Contract prompt and the source-frontmatter `disallowedTools` list.
  The compiler does not yet propagate `disallowedTools` /
  `permissionMode` into the rendered harness frontmatter, so on
  Claude Code the invariant is currently prompt-only at runtime. The
  Learn flow is uniquely exposed to this gap because Culture is its
  only stage — there is no downstream agent that could catch a
  Culture-side production write.
- **Cycle-counter persistence** — the three-cycle cap is enforced by
  the orchestrator tracking `cycle_n` in-context. There is no durable
  counter file; if the Learn session is resumed in a fresh context the
  cap resets. Persisting cycle state under
  `$TMPDIR/learn-<slug>-state.json` would close this gap.

Both gaps lower **Cross-cutting principle: Permission model per stage**
on the scoreboard, not Flow 7 itself.
