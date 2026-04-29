---
name: cheese
description: Unified entry point that inspects user input, announces detected intent, and routes to the right downstream skill (/mold, /cook, /age, /briesearch, or a debug/review flow) before dispatching.
argument-hint: "<natural language description | spec path | issue# | PR# | bug report | file path>"
---

# /cheese

`/cheese` is the single entry point for the cheese-flow workflow. Drop in any
kind of input — a half-formed idea, a spec path, a PR number, a stack trace,
or a file path — and the command inspects it, announces what it thinks you
want, and routes the work to the correct downstream skill. You always get a
chance to abort or redirect before dispatch happens.

## Intent classification

`/cheese` inspects `$ARGUMENTS` and classifies it into one of the shapes
below. The detected intent is announced back to you in plain text before any
dispatch occurs.

| Input shape | Example | Target skill |
|---|---|---|
| Feature description / rough idea | "add dark mode", "support webhooks" | `/mold` (if non-trivial) → `/cook` |
| Spec path | `<harness>/specs/add-dark-mode.md` | `/cook` |
| PR reference | `PR#142`, `https://github.com/.../pull/142` | `/age` |
| Issue reference | `#87`, `issue 87` | triage → likely `/mold` |
| Bug report / stack trace | pasted error, reproduction steps | debug flow (investigate → `/cook`) |
| File path or glob | `src/auth/login.ts`, `src/**/*.tsx` | focused review (`/age --scope`) |
| Research question | "what's the best rate limiter library?" | `/briesearch` |

`<harness>` is the active harness output root — `.claude` for Claude Code,
`.codex` for Codex.

## Dispatch contract

1. **Classify** `$ARGUMENTS` into one of the shapes above.
2. **Announce** the detected intent, the chosen target skill, and the
   one-line reason for the routing decision.
3. **Pause** for explicit confirmation. The user may redirect (e.g. "no,
   just do research first") or abort.
4. **Dispatch** only after confirmation. Never silently invoke a
   downstream skill.

## Deferred behavior

> **Scaffold notice.** The classifier and dispatcher are not yet wired.
> This file documents the intended routing contract. When invoked today,
> `/cheese` should announce the detected intent and stop — it does not yet
> invoke downstream skills automatically.

The next iteration will:

- Implement the classifier as a thin router that reads `$ARGUMENTS`.
- Wire dispatch to existing skills (`/mold`, `/cook`, `/age`,
  `/briesearch`) via the `Skill` tool.
- Add a confidence threshold: below N%, ask the user instead of guessing.
