# Context Dim — Protocol

The context reviewer checks whether the target manages its context
budget responsibly: fork vs inline, model selection with rationale,
prompt size budget, output budget, sub-agent delegation, and wrap-up
signals.

## Why this dim exists

Every token in an agent's context competes with the task. Agents that
produce or consume too much context degrade their own performance and
their orchestrator's. Context budgets are the difference between a
skill that scales across long sessions and one that pollutes the
parent's context after a few invocations.

## Decision rules

### Fork vs inline

**Fork (`context: fork`) when at least one of:**
- Output > ~500 lines (build logs, test runs, large diffs).
- Only a summary is needed by the caller, not the raw content.
- The task is independent and idempotent (re-runnable).

**Inline when all of:**
- Result is concise, immediately needed, action-relevant.
- The skill is guideline-only (no actionable task → forking returns nothing useful).

### Model selection

| Model | When |
|---|---|
| `claude-opus-4-X` | Judgment-heavy: review, architecture, complex reasoning |
| `claude-sonnet-4-X` | Implementation, exploration, most general work |
| `claude-haiku-4-X` | Focused fetch, simple transforms, token-constrained sub-agents |

Document the rationale in the agent body. A `model: claude-haiku-4-5`
declaration without prose justification is a finding (`context.missing_model_rationale`).

### Prompt size budget

| Size | Behavior |
|---|---|
| < 500 lines / ~1500 tokens | Strong instruction following |
| 500–800 lines | Risk of mid-prompt drift |
| > 800 lines | Push detail into `references/` and read on demand |

### Output budget

| Direction | Budget |
|---|---|
| Agent → caller | < 2K chars summary; write detail to `$RUN_DIR/<dim>.json` and return a pointer |
| Inline skill output | Should fit without scrolling |
| Forked sub-agent output | Caller only sees the return value; pointer pattern still recommended for very long detail |

### Wrap-up signals

Long-running agents (research loops, retry chains, scrapers) need a
tool-call cap or they run indefinitely. Pattern:

> After ~60 tool calls, wrap up the current finding and emit your
> output. Do not start a new investigation.

## Failure modes

### `context.missing_fork`

Skill produces verbose output (multi-file audits, full reports) but
runs inline. Caller's context absorbs the entire report.

### `context.fork_with_no_task`

Guideline-only skill declares `context: fork`. The sub-agent has no
actionable prompt and returns nothing useful.

### `context.missing_model_rationale`

`models.default` set without prose justification. Future maintainers
can't tell whether `haiku` was intentional or copied.

### `context.body_too_long`

Prompt body > 500 lines. Push protocol detail into `references/<topic>.md`
and read on demand.

### `context.no_output_budget`

Agent dumps full diff/test/build output to caller. Should write to
`$RUN_DIR/<dim>.json` and return a one-line summary + pointer.

### `context.no_subagent_delegation`

Agent serially tries multiple strategies (fetch from 3 sources, review
from 3 angles) when 3 parallel sub-agents would be faster and isolate
context.

### `context.no_wrap_up_signal`

Long-running loop has no tool-call cap. Risk: indefinite runtime,
context degradation.

### `context.effort_mismatch`

`metadata.effort: low` set on a judgment-heavy agent (or vice versa).
Routing model gets the wrong cost signal.

## Stake calibration

| Defect | Default bucket |
|---|---|
| `missing_fork` on a verbose-output skill | `med` |
| `fork_with_no_task` (subagent gets nothing) | `med` |
| `body_too_long` (drift risk) | `med` |
| `missing_model_rationale` | `low` |
| `no_wrap_up_signal` on a long-running loop | `med` |

## What this dim does NOT do

- Does not evaluate description trigger phrases — that's activation.
- Does not evaluate which tools are wired — that's tool-scoping.
- Does not evaluate output schema — that's output-format.
