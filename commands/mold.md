---
name: mold
description: Iterative thinking amplifier for fuzzy ideas. Routes input to a starting mode (Explore, Ground, Shape, Sketch, Grill, Diagnose), runs Validate Cycles, locks down interfaces in pseudocode, and crystallizes a spec (and optional issues) only after a two-key handshake.
argument-hint: "<rough idea | feature request | bug | spec path | design doc>"
---

# /mold

`/mold` shapes a fuzzy idea into a coherent spec (and optional issues)
that downstream `/cheese` and `/cook` can consume without re-asking
design questions. It is a **thinking amplifier**, not a one-shot
generator: the dialogue is the point, the artifact is the by-product.

## Execution

Invoke the `mold` skill with `$ARGUMENTS`. The skill owns mode routing,
Validate Cycle dispatch, interface lockdown via pseudocode, the two-key
handshake, and atomic artifact extraction to `<harness>/specs/<slug>.md`
and `<harness>/issues/<slug>-NNN.md`. `<harness>` is the active output
root for the harness in use.

Do not reimplement the dialogue or extraction logic in this command.
This file is the user-facing alias and contract; `skills/mold/SKILL.md`
is the implementation source of truth.

## Companions

| Skill | Boundary |
| --- | --- |
| `/culture` | Same dialogue feel; **never writes**. Use it when there is no artifact intent. |
| `/briesearch` | External evidence dispatcher. `/mold` calls it through the Validate Cycle. |
| `/cook` | Implements a crystallized spec. `/mold` ends with a hand-off offer, never an auto-invoke. |

## What you get

- **Spec** — rich container, written to `<harness>/specs/<slug>.md`.
  Always present unless the dialogue produced only standalone bug
  tickets.
- **Issues** — separate, GitHub-flavored, written to
  `<harness>/issues/<slug>-NNN.md`. Present when the dialogue surfaced
  side-channel actionables (out-of-scope bugs, follow-ups, parking-lot
  work).

Nothing is written until the user explicitly approves the artifact set,
slug, and target paths in a single bundled prompt.

## Use cases

- Turning "I want to add X" into an implementable spec with locked
  interfaces.
- Diagnosing a stack trace or symptom into a bug-shaped spec plus
  follow-up issues.
- Refining a half-baked design doc by stress-testing the chosen approach.
- Reading an existing spec and converging on the next iteration.

## When NOT to use

- Free-form rubber-ducking with no artifact intent → `/culture`.
- Single library lookup → `/briesearch` directly.
- Already-clear spec → skip ahead to `/cook`.
