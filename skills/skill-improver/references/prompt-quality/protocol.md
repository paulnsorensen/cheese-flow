# Prompt-Quality Dim — Protocol

The prompt-quality reviewer checks the body's clarity and structure:
sections, *why* explanations, examples, role framing, decision scaffolds,
gotchas, "What You Don't Do" sections, and (for judgment agents)
calibration scaffolds.

This dim folds the dotfiles `scoring` concern under the
`prompt-quality.missing_calibration` finding (per spec SI-1: not all
agents are judgment agents, so calibration is a sub-rubric here rather
than a standalone dim).

## Why this dim exists

Prompt structure has measurable effects on instruction following:

- Tables and bulleted rules are followed more reliably than prose.
- Rules paired with *why* generalize to edge cases; rules without it
  fail on novel inputs.
- One concrete example outperforms ten abstract rules.

## Patterns the dim looks for

### `prompt-quality.wall_of_text`

Long prose blocks where a table or bullets would scan faster. Heuristic:
> 30 consecutive lines without a heading, table, or list.

### `prompt-quality.rule_without_why`

Hard rules ("Never use `find`") with no rationale. Brittle. Pair every
rule with the reason behind it.

```
# Bad
Never use `find`.

# Good
Use `fd` instead of `find` because fd respects .gitignore and is faster
on large repos. (Rule: avoid `find`.)
```

### `prompt-quality.no_examples`

Prescriptive instructions with zero concrete examples. Add at least
one. Two establish a pattern. Three confirm it.

### `prompt-quality.verbose_role_framing`

Paragraph-long "You are..." opener instead of one tight sentence.

```
# Bad
You are a sophisticated agent designed to perform comprehensive and
thoughtful audits of agent and skill definitions, taking into account
the user's preferences and the broader project context...

# Good
You are the activation reviewer in /skill-improver. Amplify the
author's attention; do not judge for them.
```

### `prompt-quality.missing_what_you_dont_do`

Pipeline agents without an explicit "What You Don't Do" / negative
constraints section have the most scope creep with adjacent phases.

### `prompt-quality.missing_gotchas`

No "Gotchas" section. These prevent repeated failures and are the
highest-value content per token.

### `prompt-quality.missing_decision_scaffold`

Judgment task using "always/never" rules instead of a structured
scaffold (Classify → Ground → Context → Reassess; or
degrees-of-freedom). Match constraint level to risk.

### `prompt-quality.missing_calibration` (folds the `scoring` concern)

For review/audit/triage agents, no rubric for how findings are
bucketed. The agent will pattern-match the rubric description rather
than apply calibrated probabilities.

A good calibration scaffold:

1. **Classify the claim type** — base bucket + cap per type.
2. **Evidence grounding** — modifiers based on verification quality.
3. **Context modifiers** — signals that adjust severity.
4. **Re-assess borderline items** — independent second pass.

Surface as `bucket: med` for any review-intent agent missing this scaffold.

## Stake calibration

| Defect | Default bucket |
|---|---|
| `missing_what_you_dont_do` on a pipeline agent | `med` |
| `missing_calibration` on a judgment agent | `med` |
| `wall_of_text` (cosmetic) | `low` |
| `rule_without_why` | `low` |
| `verbose_role_framing` | `low` |

## What this dim does NOT do

- Does not evaluate description routing copy — that's activation.
- Does not evaluate tool reachability — that's tool-scoping.
- Does not evaluate output schema or summary-first structure — that's output-format.
