---
name: age
description: Staff Engineer code review. Runs six parallel review dimensions (safety, architecture, encapsulation, YAGNI, spec, history risk) and returns a unified scored report with only findings at confidence >= 50.
argument-hint: "[--comprehensive] [--scope <path>] [<diff or change ref>]"
metadata:
  owner: cheese-flow
  version: "0.1.0"
  status: scaffold
---

# /age

`/age` is a Staff Engineer code review. It evaluates code across six
independent dimensions in parallel and returns a unified Age Report with
scored findings. Only findings at confidence >= 50 are surfaced.

## Modes

| Mode | Trigger | Scope |
|---|---|---|
| Focused (default) | no flag | Recent changes on the current branch, or an explicit diff / change ref |
| Comprehensive | `--comprehensive` | Full module audit against the spec and engineering principles |
| Scoped | `--scope <path>` | A specific file, folder, or glob |

## Review dimensions

Each dimension will run as an independent parallel sub-agent. All findings
use a 0-100 confidence scale; only >= 50 is surfaced to the user.

| Dimension | Sub-agent | What it looks for |
|---|---|---|
| Safety | `fromage-age-safety` | Bugs, security holes, silent failures, unchecked inputs |
| Architecture | `fromage-age-arch` | Complexity budgets (lines, params, nesting), Sliced Bread organization |
| Encapsulation | `fromage-age-encap` | Leaky abstractions, overly wide public APIs, cross-boundary imports |
| YAGNI / de-slop | `fromage-age-yagni` | Unjustified dead code, speculative abstractions, AI-generated noise |
| Spec adherence | `fromage-age-spec` | Drift from `.claude/specs/<slug>.md`, monkey patches, shortcuts |
| History risk | `fromage-age-history` | Per-file risk modifiers derived from git blame / churn patterns |

## Output contract

`/age` returns a single Age Report with:

- A one-line summary per dimension.
- Findings grouped by severity, each including the dimension, score,
  rationale, and a `file_path:line_number` anchor the user can jump to.
- History-risk modifiers applied to sibling findings (not surfaced on
  their own).
- A clear "no significant findings" result if all dimensions return
  scores below 50.

## Deferred behavior

> **Scaffold notice.** Parallel sub-agent dispatch is not yet wired. This
> file documents the review contract. The current implementation should
> describe what `/age` would do and stop — it does not yet spawn the six
> dimension agents.

The next iteration will:

- Spawn the six dimension sub-agents in parallel via the `Agent` tool.
- Aggregate findings, apply the 50-point surface threshold, and merge
  history risk modifiers into sibling findings.
- Emit the unified Age Report as a single response.
