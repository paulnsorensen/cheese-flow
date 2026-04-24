---
name: mold
description: Spec writer. Runs a focused dialogue to shape a feature, surfaces at least two approaches with trade-offs, and saves the resulting spec to <harness>/specs/<slug>.md only after explicit user approval.
argument-hint: "<rough idea | feature request | issue reference>"
---

# /mold

`/mold` shapes a rough idea into an implementable spec. It runs a focused
dialogue — one clarifying question at a time — and saves the result to
`<harness>/specs/<slug>.md` only after you explicitly approve. `<harness>`
is the active harness output root — `.claude` for Claude Code, `.codex`
for Codex.

## Dialogue style

- **One question at a time.** No interrogation lists. Each question
  follows from the previous answer.
- **Always surface alternatives.** Any non-trivial spec produces at least
  two viable approaches with their trade-offs. "Do nothing" is always a
  candidate and must be considered.
- **Approval gate.** Nothing is written to `<harness>/specs/` until the user
  says yes.

## Spec skeleton

The final spec always includes these sections, in this order:

1. **Problem.** What is broken, missing, or painful today.
2. **Goals.** What must be true when this is done.
3. **Non-goals.** Explicit scope boundaries — what is OUT.
4. **Approach.** The chosen approach, with a brief note on alternatives
   considered and why they were rejected.
5. **Risks.** Known risks, unknowns, and mitigations.
6. **Quality gates.** The exact commands that must pass for this to be
   considered done (e.g. `npm test`, `cargo clippy`).
7. **Open questions.** Anything still unresolved at approval time.

## Hand-off

Specs produced by `/mold` are designed to be consumed by:

- `/fromagerie` for large features that decompose into many independent
  work units.
- `/fromage` for single coherent features.
- `/cheese` (top-level router), which may redirect an idea to `/mold`
  before implementation.

Running `/mold` before `/cheese` or `/fromage` is strongly recommended
for anything above trivial complexity.

## Deferred behavior

> **Scaffold notice.** The conversational loop and approval-gated write
> to `<harness>/specs/` are not yet wired. This file documents the spec
> skeleton and the dialogue contract. The current implementation should
> describe what `/mold` would produce and stop — it does not yet run the
> interactive session or write any files.

The next iteration will:

- Implement the single-question-at-a-time dialogue.
- Enforce the "surface at least two approaches" rule on every non-trivial
  spec.
- Gate the write to `<harness>/specs/<slug>.md` behind explicit user
  approval via `AskUserQuestion`.
