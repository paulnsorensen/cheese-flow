---
name: critique
description: >
  Fresh-context per-charter critic dispatcher. Spawns a single critic sub-agent
  (cook-critic, culture-critic, …) in a clean window with an artifact handle,
  task text, and producer claim — the critic re-derives findings from primary
  sources rather than trusting the producer's summary. Use after a producer
  step inside a flow (e.g. between Cook and Press) to catch issues before the
  next stage runs. Distinct from `/age`: critique is intra-execution and
  single-dimensional (one rubric per producer); /age is post-implementation
  and multi-dimensional (six dimensions, flow-terminal). Do NOT use for fresh
  spec writing (mold), implementation (cook), or PR comment triage (respond).
license: MIT
compatibility: Works in any harness that supports first-level subagent dispatch.
allowed-tools:
  - read
  - write
  - bash
metadata:
  owner: cheese-flow
  pattern: self-refinement
  citations:
    - "Madaan 2023 (arxiv 2303.17651) — Self-Refine (anti-pattern motivation)"
    - "Shinn 2023 (arxiv 2303.11366) — Reflexion (target pattern)"
    - "Xu et al. ACL 2024 — Pride and Prejudice: LLM Amplifies Self-Bias in Self-Refinement"
---

# critique

Dispatch a per-charter critic in a fresh context window. The critic receives
only an artifact handle and re-derives findings from primary sources — never
trusts the producer's summary.

## Why fresh context

Same-context self-critique provably amplifies self-bias across iterations
(Xu et al., ACL 2024). The mitigation is independent feedback. cheese-flow
embodies this as **per-charter critics dispatched fresh** — one critic per
producer charter (cook-critic for cook, culture-critic for culture, …), each
with its own rubric (production-code review vs architectural-mental-model
review, etc.). Per-charter keeps the rubric specific; fresh-context keeps the
critic structurally isolated from the producer's session history.

This is intentionally NOT `/age`:

| | `/critique <producer>` | `/age` |
|---|---|---|
| Stage | intra-execution (between producer and next stage) | post-implementation (flow-terminal) |
| Dimensions | single (the producer's rubric) | six (safety / arch / encap / yagni / history / spec) |
| Caller | flow orchestrator (fromage / explore / pr-finish / debug) | user or end-of-flow |

## Arguments

The skill expects the following arguments (parsed from `args`):

- `--producer <name>` — required. Maps to an existing critic agent
  (`<name>-critic`). Currently supported: `cook`, `culture`. Future:
  `cut`, `press`.
- `--artifact <path>` — required. Canonical handle to the producer's output.
  Typically `$TMPDIR/<flow>-<producer>-<slug>.md` (matches the writer-trio's
  compaction-seam contract) but a git SHA range or spec path is also valid.
  The critic re-reads this independently.
- `--task <inline-or-path>` — required. The original user request or
  producer's plan. May be a literal string or a path to a file containing it.
- `--slug <slug>` — required. Kebab-case identifier for the artifact pair.
  Used to namespace the critic's output at `$TMPDIR/critique-<producer>-<slug>.md`.

## Protocol

### Step 1: Validate

Confirm `--producer <name>` maps to an existing
`agents/<name>-critic.md.eta`. If not, fail fast with a clear error listing
supported producers.

### Step 2: Dispatch fresh

Spawn the critic in a single Agent call:

```
Agent(
  subagent_type="<producer>-critic",
  prompt="""
Producer reports may be incomplete or optimistic. You MUST verify everything
independently from the artifact handle.

## Envelope

- task: <verbatim from --task; if path, read it first>
- producer_claim: <max 1500 chars from the producer's terse summary; the
  full body lives at the artifact handle>
- artifact_handle: <verbatim from --artifact>
- rubric: see your charter

## Your job

1. Re-read the artifact at the handle. Do not trust the producer_claim.
2. Re-derive findings from primary sources (re-run `git diff` if the handle
   is a SHA range; re-read the spec if the handle is a spec path; re-read
   the file if the handle is a $TMPDIR path).
3. Score findings 0-100. Surface only findings >= 50.
4. Write the full critique report to $TMPDIR/critique-<producer>-<slug>.md.
5. Return the structured summary (max 1500 chars) per your charter's
   Output contract.
"""
)
```

### Step 3: Return

Read `$TMPDIR/critique-<producer>-<slug>.md`. Return the critic's structured
summary (the short findings table, max 1500 chars) to the orchestrator.

The full body remains in $TMPDIR for downstream stages to consult.

## Rules

- **Single critic per call** — this skill dispatches exactly one critic.
  Multi-rubric reviews use `/age` instead.
- **Fresh context only** — never embed the critic into the caller's session;
  always dispatch via `Agent(subagent_type=...)`.
- **No producer trust** — the critic's prompt must explicitly instruct
  re-derivation from primary sources. The 1500-char `producer_claim` is
  context, not ground truth.
- **Confidence gating** — surface only findings scored >= 50, matching the
  cheese-flow scoring convention.
