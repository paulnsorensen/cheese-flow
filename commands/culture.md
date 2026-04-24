---
name: culture
description: Free-form rubber-ducking and architecture exploration. Hard invariant is no writes to production files; the goal is a shared mental model, not code, spec, or PR output.
argument-hint: "<question | half-formed idea | design problem>"
---

# /culture

`/culture` is a thinking space. Use it to rubber-duck a design, walk
through an architecture change, or talk out an ambiguous problem before
you decide what to actually build.

## Hard invariant: no writes

`/culture` **never writes to production files.** No code changes, no
spec file, no PR, no commits. The output is conversation — shared
understanding you can take into another skill.

If the dialogue discovers that something concrete should be built or
written, `/culture` ends the session and recommends the correct next
skill. It does not cross the line itself.

## What `/culture` IS

- Exploring architecture trade-offs out loud.
- Walking through what would change if you implemented approach A vs B.
- Mapping the blast radius of a hypothetical refactor.
- Naming the real problem before jumping to a solution.
- Thinking together about a design that is not yet a decision.

## What `/culture` is NOT

| If you want to… | Use instead |
|---|---|
| Implement a feature | `/fromage` |
| Write a spec to a file | `/mold` |
| Review existing code | `/age` |
| Research an external library or API | `/briesearch` |

## Exit criterion

The session ends when the user has a clear-enough mental model to move
forward — either by invoking another skill, by deciding not to do the
work, or by pausing. An optional short summary may be returned to the
user; no file is written.

## Deferred behavior

> **Scaffold notice.** The conversational protocol and the "no writes"
> enforcement are not yet wired. This file documents the invariants and
> contract. The current implementation should surface the invariant and
> describe how it would engage, then stop.

The next iteration will:

- Implement the rubber-ducking dialogue loop.
- Enforce the no-writes invariant at the tool-use layer (no `Write`,
  `Edit`, `NotebookEdit`, or git-mutating Bash calls).
- Provide a short, optional, user-facing summary at session end.
