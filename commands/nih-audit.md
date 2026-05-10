---
name: nih-audit
description: Whole-repo audit for code that reinvents what open-source libraries already do. Detects hand-rolled retry, validation, UUID, debounce, date, argparse, and other common patterns; cross-checks against installed dependencies; returns scored migration recommendations with effort estimates.
argument-hint: "[scope path, default repo root]"
---

# /nih-audit

`/nih-audit` finds code reinventing the wheel and recommends the libraries
that already do the job. Every recommendation is scored against the project's
installed dependency manifests, with effort estimates and a documented
"why not" so you can keep the NIH on purpose if that was the point.

## Execution

Invoke the `nih-audit` skill with `$ARGUMENTS` as the scope (default: repo
root). The skill owns manifest discovery, structural NIH scanning via
`nih-scanner`, parallel library research, spec/intent alignment, two-pass
scoring, and report emission.

Do not reimplement orchestration in this command. This file is the
user-facing alias and contract; `skills/nih-audit/SKILL.md` is the
implementation source of truth.

## Companions

| Skill | Boundary |
| --- | --- |
| `/age` (`nih` dim) | **Diff-scoped**. Flags newly introduced NIH in a single PR. Use for review gating. |
| `/mold` (Sketch NIH probe) | **Pre-implementation**. Catches NIH before a signature is locked. Use during design. |
| `/briesearch` | Library discovery dispatcher. `/nih-audit` calls it once per category group. |

## What you get

- `.cheese/nih/<slug>.md` — full report with summary table and one
  detailed `### Finding` block per candidate.
- Each finding carries: NIH code reference, recommended library with
  download/stars/licence/maintenance signals, code touchpoints, effort
  size (S / M / L), migration plan, two-pass scoring with average, plus
  honest "why not" reasoning.

The skill never auto-invokes a follow-up. Migration is a human decision.

## When to use

- Before a major refactor — establish the build-vs-buy baseline.
- After inheriting a codebase — see what utility folders are quietly
  reinventing.
- During tech-debt sprints — generate a prioritized migration list.
- When wondering "isn't there a library for this?" — the answer plus
  the migration plan in one shot.

## When NOT to use

- Single-PR review → use `/age` (the `nih` dim is diff-scoped).
- Pre-design library check → use `/mold` (Sketch mode includes the NIH probe).
- Security-only scan → use `/audit`.
- General code review → use `/age` or `/code-review`.
