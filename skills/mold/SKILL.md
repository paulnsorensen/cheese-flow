---
name: mold
description: Iterative thinking amplifier for fuzzy ideas. Routes input to the right starting mode (Explore, Ground, Shape, Sketch, Grill, Diagnose), runs Validate Cycles to anchor claims, locks down interfaces in pseudocode, and only crystallizes a spec (and optional issues) after a two-key handshake plus a coherence self-check.
license: MIT
compatibility: Works in markdown-based coding harnesses with sub-agent support. Heavy delegation to /briesearch and cheez-* skills; degrades gracefully when those are absent.
metadata:
  owner: cheese-flow
  category: planning
allowed-tools:
  - read
  - write
  - bash
  - subagent
---
# /mold

Use this skill when the user has a fuzzy idea and wants to converge — through
dialogue, evidence, and interface lockdown — on a coherent spec (and optional
issues) that downstream `/cheese` and `/fromage` can consume without
re-asking design questions.

Do not use this skill for one-shot implementation, free-form rubber-ducking
without artifact intent (use `/culture`), or library-only research (use
`/briesearch` directly).

## What `/mold` is

A **thinking amplifier**, not a pre-prompt. The dialogue is the point;
artifacts are the by-product. The terminal step crystallizes whatever the
dialogue actually produced — never more, never less.

| Companion | Boundary |
| --- | --- |
| `/culture` | Same dialogue feel; **never writes**. Use it when there is no artifact intent. |
| `/briesearch` | External evidence dispatcher. `/mold` calls it through the Validate Cycle. |
| `/fromage` | Implements a crystallized spec. `/mold` ends with a hand-off offer, never an auto-invoke. |

## Operating principles

1. **No fixed entry point.** Inspect input shape and pick a starting mode.
   Announce the mode in one line. Low-confidence classifications default to
   `Explore`.
2. **Ground every load-bearing claim.** Never speculate about local code or
   external behavior without a `cheez-*` call or a Validate Cycle.
3. **State a hypothesis before researching.** A bare research dispatch is
   discouraged; the Validate Cycle frame forces commitment plus a judgment
   step.
4. **Lock down interfaces before crystallizing.** Every cross-module seam
   gets a pseudocode signature with named unknowns and a recommended answer.
5. **Two-key handshake.** Both the user (explicit verb) and the agent
   (coherence self-check) must agree before extraction.
6. **Heavy delegation.** `/briesearch` for external research, `cheez-search`
   / `cheez-read` for in-repo grounding. Do not reinvent.
7. **No production writes during the loop.** The only writes happen on
   Crystallize, after explicit approval.

## Routing — input shape to starting mode

| Input shape | Start mode | Heuristic |
| --- | --- | --- |
| Stack trace, "X is broken/slow/flaky" | Diagnose | error markers, `file:line` refs, symptom verbs |
| File path, PR ref, existing spec under `<harness>/specs/` | Ground | concrete artifact exists; read it first |
| Half-baked design doc with signatures or schemas | Sketch | already has interfaces; refine them |
| "I want to add X" with concrete nouns | Shape | named the thing → jump to options |
| "Should we do X? thinking about Y" | Grill | tentative plan exists → stress-test it |
| Vague noun, half-sentence, "thinking about" | Explore | no grounded artifact, no chosen direction |

Detail in `references/routing.md`.

## The six modes

Crystallize is a terminal state, not a mode.

### Explore — intent extraction
Job: collapse ambiguity with high-leverage questions. Borrow the `Beat 0`
framing (Job-To-Be-Done, Why Now, What This Unlocks, Who Has The Pain, Do
Nothing). Use lettered options to compress decisions.
Exit when: a problem statement plus one concrete pain point is articulated.

### Ground — anti-hallucination
Job: anchor every claim to evidence — code, docs, prior research. Probe
glossary conflicts against any harness convention files (`CONTEXT.md`,
`CLAUDE.md`, project root agent guides) found on entry.
**Sharpen fuzzy language**: when the user uses overloaded or ambiguous
terms ("account", "session", "user"), pause and resolve with a
canonical-term question (e.g. "you said 'account' — do you mean Customer
or User? Those are different things"). Resolved terms get logged in the
state file's `Decisions` block so later modes use the canonical name.
Invariant: never say "I think the code does X" without a `cheez-*` call.
Exit when: every load-bearing claim has a citation.

### Shape — option generation
Job: turn a grounded problem into 2+ candidate approaches with trade-offs.
Always include `Do Nothing`. Recommend with one-line rationale. Validate
Cycle any load-bearing assumption behind a recommendation.
Exit when: an option is picked (→ Sketch) or none survive (→ Explore).

### Sketch — interface lockdown
Job: lock modules, responsibilities, I/O contracts, and seams in pseudocode
signatures. Before drafting, parallel `cheez-search` for sibling signatures
in the same domain so new ones fit conventions.
Exit when: every public seam has a signature; every cross-module call has a
contract. Detail in `references/sketch-mode.md`.

### Grill — adversarial clarification
Job: stress-test the chosen approach plus sketched interfaces. **One question
at a time**, paired with the agent's recommended answer. The recommendation
is non-optional. Traverse decision branches and contract corners. When grill
surfaces an unverified assumption, pause and run a Validate Cycle.
Exit when: every branch and contract corner is touched and agent confidence
is at least user confidence.

### Diagnose — symptom inputs
Job: entry mode for stack traces and "X is broken". Phases:
`Build a Loop → Reproduce → Hypothesize (3-5 ranked, falsifiable, parallel
Validate Cycles) → Confirm root cause`. Phase 0 (**Build a Loop**) is the
core discipline — agree on a fast, deterministic, falsifiable feedback
technique (failing test, curl/CLI script, headless browser, replay,
bisection harness, differential loop, ...) before chasing hypotheses.
The chosen loop becomes the Reproduction block in the bug-shaped spec, so
`/fromage` can verify the fix against the same signal the diagnosis used.
Diagnose is **diagnostic-only** — hand-off to Shape ("what's the fix?")
then Crystallize emits a bug-shaped spec plus optional follow-up issues.
Loop menu and discipline in `references/diagnose-mode.md`.

## The Validate Cycle (cross-mode sub-pattern)

Any mode can invoke it. Always **announce the cycle** before dispatching.

```
Launching a validate cycle on hypothesis: "<single declarative sentence>"

Plan:
  /briesearch  — fetch evidence
  Judge        — support, contradict, or refine?
  Settle       — accept, revise, or reject. Continue from current mode.
```

Outcomes write to the state file's `Validate cycles` block:

- **SUPPORTED** — evidence aligns; hypothesis becomes a decision.
- **CONTRADICTED** — evidence disagrees; surface as `[CONFLICT]`; revise or
  abandon.
- **REFINED** — evidence partially aligns; restate with new precision and
  re-validate or accept.

Diagnose's parallel hypothesis ranking is the cycle, parallelized.

Cap: max **two** `/briesearch` calls per session unless the user requests
more. Cycles backed by `cheez-*` evidence alone are unbudgeted.

Detail in `references/validate-cycle.md`.

## Sub-agent dispatch

| Tool | When | Cap |
| --- | --- | --- |
| `/briesearch` (via Validate Cycle) | hypothesis needs external evidence | 2/session |
| `cheez-search` | symbol mention, dependency claim, callers/imports lookup, sibling lookup | unbudgeted |
| `cheez-read` | file mention, spec read on entry | unbudgeted |

`cheez-search` covers blast-radius work via its `kind: "callers"` mode and
`tilth_deps` tool — use it instead of looking for a separate dependency
skill.

**Parallel sweeps**:

- *Shape Sweep* — one turn fans out 3-4 `cheez-search` reads (symbol +
  callers + deps) plus optional `/briesearch` before drafting Options.
- *Sketch Sweep* — parallel `cheez-search` for nearby siblings before drafting
  signatures for a module.
- *Hypothesis Probe (Diagnose)* — parallel Validate Cycles, one per ranked
  hypothesis.

## State tracking

Scratch state file at `${TMPDIR:-/tmp}/cheese-flow-mold-<run_id>/state.md`.
Mirrors `/briesearch`'s scratch pattern: portable, auto-evicted post-session.

The file records mode, input summary, decisions, locked sketches, validate
cycles with outcomes, open questions with markers, and mode history. Schema
in `references/state-schema.md`.

## User knobs (free-form interrupts)

`explore`, `ground`, `shape`, `sketch`, `grill`, `diagnose`,
`validate <hypothesis>`, `crystallize`, `pause`, `enough`. The agent honours
these immediately. `crystallize` initiates the handshake; it does not skip
the Sketch gate unless the user follows up with `crystallize anyway`.

## Uncertainty markers

| Marker | Meaning |
| --- | --- |
| `[?]` | Agent uncertain; needs validation |
| `[TBD]` | User uncertain; decision deferred |
| `[BLOCKED]` | External dependency unresolved |
| `[CONFLICT]` | Codebase contradicts a stated assumption |

## Termination — two-key handshake

**User key:** explicit `crystallize`, `ship it`, `extract`, `that's enough`.
Never inferred.

**Agent key:** structured coherence self-check. Print this checklist and
require every box checked before extraction (or an explicit override):

```
Coherence self-check before crystallize:
- [ ] Problem statement: grounded, agreed
- [ ] At least 2 options weighed (Do Nothing included)
- [ ] Chosen option grounded in codebase evidence
- [ ] Interface sketches: every public seam has a pseudocode signature
- [ ] Validate cycles: all launched cycles judged
- [ ] Chosen option Grilled (>=1 question per major branch)
- [ ] Open questions all marked [TBD] / [BLOCKED] / [?] (none silent)
- [ ] Quality gates specified
```

Guard conditions are mandatory before Crystallize except where noted:

- *Ground gate* — at least one Ground pass with a citation before Shape's
  options. Exception: pure greenfield (the agent must say so).
- *Shape gate* — at least one Option block weighed (Do Nothing counts).
- *Sketch gate* — mandatory when the chosen option touches more than one
  module or introduces a new public interface. Skip only for trivial
  single-function changes (the agent must say so).
- *Grill gate* — mandatory for high-blast-radius decisions, where blast
  radius is measured by `cheez-search` callers/imports for the touched
  symbols.
- *Open hypotheses must settle* — any Validate Cycle launched but unjudged
  blocks Crystallize unless the user accepts it as `[TBD]`.

If any box is unchecked, name it and propose the smallest move to fill it.
The user can override with `crystallize anyway`.

## Crystallize — artifact extraction

Two artifact types:

- **Spec** — the rich container; absorbs problem framing, requirements,
  approach, decisions, interface sketches, risks, gates. Always present
  unless the dialogue produced only standalone bug tickets. Template in
  `references/spec.md`.
- **Issue** (1..N) — separate, GitHub-flavored, when the dialogue surfaced
  actionable items independent of the main spec scope. Template in
  `references/issue.md`.

Format selection table:

| Dialogue signal | Output |
| --- | --- |
| Any meaningful design discussion | Spec |
| Side-channel actionables (out-of-scope bugs, follow-ups) | Spec + Issues (`bug`/`chore` flavor) |
| Plan broke down into independently-grabbable atoms | Spec + Issues (`slice` flavor — vertical slices, AFK/HITL, blocked-by graph) |
| Diagnose root cause + fix design | Spec (bug-shaped) + optional Issues |
| Pure decision-only (no design) | Spec with only `Decisions` populated |

Confirm in **one** approval prompt covering the artifact set, the slug, and
the target paths. Render drafts inline first if the user wants to iterate
before any disk writes.

Output paths (relative to the active harness output root, surfaced as
`<harness>/...`):

| Output | Path |
| --- | --- |
| Spec only | `<harness>/specs/<slug>.md` |
| Issues only | `<harness>/issues/<slug>-001.md`, `-002.md`, ... |
| Spec + Issues | spec at `<harness>/specs/<slug>.md`; issues at `<harness>/issues/<slug>-001.md`, ... |

Slug derivation: lowercase the working problem statement, drop stopwords,
kebab-case, cap at 5 words. Honour user-passed slugs verbatim.

Collisions:

| Existing | Action |
| --- | --- |
| Same slug, status `draft` | Overwrite (default) or rev (`<slug>-v2`) |
| Same slug, status `approved` | Default rev; never silently overwrite |
| Existing spec, new issues for same slug | Append issues to that slug's series |

Confidence is tagged twice — document-level in spec frontmatter (mechanical
formula in `references/spec.md`) and inline at decision points in the
spec body.

Write atomically: stage to a temp directory, then move into place. Never
leave partial files on a write failure.

## Hand-off

After writing, offer the next step inline. Never auto-invoke.

| Artifact | Suggested next step |
| --- | --- |
| Spec (single feature) | `/fromage <harness>/specs/<slug>.md` |
| Spec (large) | `/fromagerie <harness>/specs/<slug>.md` |
| Issues | `gh issue create --body-file <path>` (per file) |

## Loop detection

The session can stall. The agent watches for:

- *Drift* — 4 consecutive turns without a new `Decisions`, `Sketches`, or
  `Validate cycles` entry → surface, propose summary or pause.
- *Bored user* — terse responses, repeated `meh` → surface escape hatches.
- *Rabbit hole* — 3+ mode transitions in the last 5 turns and no new state
  entries → forced synthesis turn.

Rules in `references/loop-detection.md`.

## Rules

- Do not write to production paths during the dialogue. Only Crystallize
  writes files, only after the two-key handshake.
- Do not direct-call `/briesearch` for unstated questions; wrap external
  evidence in a Validate Cycle.
- Do not skip the Sketch gate for non-trivial features without an explicit
  declaration.
- Do not silently drop open hypotheses; they must settle or be marked
  `[TBD]`.
- Do not overwrite an `approved` spec without explicit user opt-in.
- Do not attempt to implement code; pseudocode signatures are plan, not code.
