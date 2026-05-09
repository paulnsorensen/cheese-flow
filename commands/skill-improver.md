---
name: skill-improver
description: Audit an agent or skill definition file. Runs five orthogonal LLM dimensions (activation, tool-scoping, context, prompt-quality, output-format) over a single agent or skill source file and emits a stake-weighted report plus hash-anchored sidecar JSON consumed by /cleanup.
argument-hint: "<agent-path | skill-path>"
---

# /skill-improver

`/skill-improver` is an evidence-first auditor for cheese-flow's own agent
and skill definitions. It surfaces where to look and why, with verifiable
evidence per observation, so the author can decide what to act on instead
of accepting a verdict on faith.

Five orthogonal dimensions fan out in parallel over a single target file.
Each dimension emits evidence-backed observations. The orchestrator
synthesizes a stake-weighted report and two sidecar JSON files for
downstream automation.

## Execution

Invoke the `skill-improver` skill with `$ARGUMENTS`. The skill owns
target classification, evidence pre-fetch, parallel dim dispatch,
synthesis, sidecar emission, and cleanup.

Do not reimplement orchestration in this command. This file is the
user-facing contract; `skills/skill-improver/SKILL.md` is the implementation.

## Dimensions

| Dim | Stake | What it reviews |
|---|---|---|
| `activation` | high | Description as trigger spec, trigger phrases, third-person voice, negative triggers, portable frontmatter invocation fields |
| `tool-scoping` | high | Read-only / write-scoped / focused-sub-agent tier match; reachable write tools versus prose claims; `skills:` aligned with delegation |
| `context` | medium | Fork vs inline decision, model rationale, prompt-size budget, output budget, wrap-up signals |
| `prompt-quality` | medium | Structured sections, *why* explanations, examples, decision scaffolds, "What You Don't Do" sections, calibration scaffolds for judgment agents |
| `output-format` | medium | Summary-first layout, scannable tables, threshold tally, detail-vs-summary separation, structured output for downstream consumers |

All 5 dims fire on every run. Dims whose rubric does not apply emit
`scope_match: false` and are tallied but not rendered as sections.

## Output Contract

Three artifacts written to `.cheese/skill-improver/<slug>.*`:

- **`<slug>.md`** — stake-weighted Markdown report:
  - Orientation paragraph (target kind, model tier, tool surface, line count)
  - Tally line (ran 5; N had findings)
  - High-stake dims → medium-stake dims
  - Cross-dimension callouts (loci where 2+ dims agree)
- **`<slug>.fixes.json`** — hash-anchored, mechanically-applicable fixes
  ready for `tilth_edit`. Consumed by `/cleanup` (same schema as `/age`).
- **`<slug>.suggestions.json`** — narrative-shaped guidance keyed by
  observation `id`. Consumed by `/fromage cook`.

Confidence is bucketed (`low | med | high`). No numeric scores anywhere
in the output.

## Hand-off

`/skill-improver` performs no writes to source files. After the report
prints, the next step is yours:

```
/cleanup skill-improver/<slug>         — apply mechanical fixes
/fromage cook --suggestions <slug>     — act on judgment guidance
```

The amplifier-pure boundary forbids auto-invoke (FR-8). The report is
the deliverable; action is the user's call.

## When to Use

- Before merging a new agent or skill to catch activation, tool-scoping,
  and context defects.
- After writing initial agent/skill code to validate frontmatter contracts.
- Anytime you want evidence-backed observations rather than a verdict.

## What this command does NOT do

- Does not generate new agents or skills from scratch — that is `/skill-creator`.
- Does not audit arbitrary external agents or skills unless they follow
  cheese-flow's frontmatter and sidecar contracts.
- Does not apply fixes — `/cleanup` does that, and only after you ask it to.
