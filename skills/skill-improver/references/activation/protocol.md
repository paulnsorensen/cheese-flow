# Activation Dim — Protocol

The activation reviewer treats the `description` field as a **trigger
specification** for the routing model, not a summary for humans. It also
inspects frontmatter routing fields that affect when and how the target
is invoked.

## Why this dim exists

Skills under-trigger at a baseline of ~20%. Most of the gap is structural,
not semantic: routing models match on **explicit phrasing** that the
description provides, not on inferred intent. A description that reads
as a summary ("A tool for X") is a routing miss.

## Three-part description pattern

Effective descriptions follow:

```
[Core capability]. [Secondary capabilities]. Use when [trigger1],
[trigger2], or when user mentions "[keyword1]", "[keyword2]".
```

Stronger when it ends with `or invokes /<command-name>` so the routing
model can also match on slash-command intent.

## Failure modes (with examples)

### `activation.summary_not_trigger`

```yaml
# Bad
description: A tool for reviewing PR comments.

# Good
description: Review PR comments and route fixes. Use when the user says
  "audit pr", "review feedback", "respond to PR", or invokes /respond.
```

### `activation.first_person_voice`

The description is injected into the routing model's system prompt.
First-person breaks the framing.

```yaml
# Bad
description: I review PR comments and propose fixes.

# Good
description: Reviews PR comments and proposes fixes.
```

### `activation.missing_negative_triggers`

When two skills have adjacent domains, both routing decisions are
ambiguous. Negative triggers disambiguate.

```yaml
# /skill-improver
description: ... Do NOT use for creating new skills from scratch — use
  /skill-creator for that.
```

### `activation.keyword_gap`

The description must list synonyms users actually say. Missing common
phrasings = missed activations.

| Concept | Cover at least these |
|---|---|
| review | review, audit, check, inspect, evaluate |
| improve | improve, optimize, tighten, refactor, clean up |
| trigger | trigger, activate, fire, route, match |

### `activation.routing_field_misuse`

Frontmatter routing fields with documented semantics:

| Field | When to set |
|---|---|
| `disable-model-invocation: true` | Destructive or infrequently-needed skills (only `/cmd` triggers) |
| `effort: high` | Research-heavy or judgment-heavy skills |
| `effort: low` | Simple formatting / fetch tasks |
| `user-invocable: false` | Background skills that should not appear in `/` menu |
| `context: fork` | Skill reads ≥30 files or produces verbose output |
| `agent` | Pairs with `context: fork` to specify subagent type |

Common defects:

- `context: fork` on a guideline-only skill (no actionable task → empty subagent)
- `disable-model-invocation` missing on a destructive skill
- `effort: low` on a judgment-heavy review skill

### `activation.name_directory_mismatch`

For skills, `frontmatter.name` must equal the parent directory name
(enforced by `lint-skills-directory`). Surface as `bucket: high` because
linting will fail outright.

## What this dim does NOT do

- Does not evaluate prompt body quality — that's prompt-quality.
- Does not evaluate tool reachability — that's tool-scoping.
- Does not evaluate output structure — that's output-format.
