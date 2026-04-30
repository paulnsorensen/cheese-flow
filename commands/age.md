---
name: age
description: Staff Engineer code review. Runs eight orthogonal LLM dimensions (correctness, security, complexity, encapsulation, spec, precedent, deslop, assertions) over the diff and emits a stake-weighted report plus hash-anchored sidecar JSON consumed by /cleanup and /fromage cook.
argument-hint: "[<ref>] [--scope <path>] [--comprehensive]"
---

# /age

`/age` is a Staff Engineer code review. It surfaces where to look and why,
with verifiable evidence per observation, so you can decide what is actually
a problem instead of accepting a verdict on faith.

Eight orthogonal dimensions fan out in parallel over your diff. Each dim
emits evidence-backed observations. The orchestrator synthesizes a
stake-weighted report and two sidecar JSON files for downstream automation.

## Execution

Invoke the `age` skill with `$ARGUMENTS`. The skill owns evidence pre-fetch,
parallel dim dispatch, synthesis, sidecar emission, and cleanup.

Do not reimplement orchestration in this command. This file is the
user-facing contract; `skills/age/SKILL.md` is the implementation.

## Dimensions

| Dim | Stake | What it reviews |
|---|---|---|
| `correctness` | high | Silent failures, error swallowing, null misuse, ordering bugs |
| `security` | high | Diff-scoped auth bypass, secrets, taint-shaped concerns |
| `encapsulation` | high | Sliced Bread compliance, cross-slice imports, public-API width |
| `spec` | high | Drift between `.cheese/specs/<slug>.md` and touched code |
| `complexity` | medium | Function ≤40 lines, file ≤300, params ≤4, nesting ≤3 |
| `deslop` | medium | AI anti-patterns, dead code, speculative abstractions |
| `assertions` | medium | Weak test assertions, existence checks, catch-all errors |
| `precedent` | advisory | Symbol-level history, concurrent PRs touching same paths |

All 8 dims fire on every run. Dims whose rubric does not apply emit
`scope_match: false` and are tallied but not rendered as sections.

## Output Contract

Three artifacts written to `.cheese/age/<slug>.*`:

- **`<slug>.md`** — stake-weighted Markdown report:
  - Orientation paragraph (what the diff does, factual)
  - Tally line (ran 8; N had findings)
  - High-stake dims → medium-stake dims → advisory dims
  - Cross-dimension callouts (loci where 2+ dims agree)
- **`<slug>.fixes.json`** — hash-anchored, mechanically-applicable fixes
  ready for `tilth_edit`. Consumed by `/cleanup`.
- **`<slug>.suggestions.json`** — narrative-shaped guidance keyed by
  observation `id`. Consumed by `/fromage cook`.

Confidence is bucketed (`low | med | high`). No numeric scores anywhere
in the output.

## Hand-off

`/age` performs no writes to production source files. After the report
prints, the next step is yours:

```
/cleanup <slug>                        — apply mechanical fixes
/fromage cook --suggestions <slug>     — act on judgment guidance
```

## When to Use

- Before merging a PR you want a structured map of before approving.
- After `/cook` to catch correctness and encapsulation issues before press.
- In `/fromage` as the gate between cook and press phases.
- Anytime you want evidence-backed observations rather than a verdict.
