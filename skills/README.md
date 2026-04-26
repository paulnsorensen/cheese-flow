# Portable Skill Sources

Top-level `skills/` is the canonical source directory for portable skill definitions.
The compiler in `src/` reads these sources, validates their frontmatter, and emits
harness-specific artifacts for Claude Code, Codex, Cursor, Copilot CLI, and future
targets.

`src/` should contain compiler code and harness adapters. It should not contain the
canonical skill content.

## Source Model

Each skill lives in its own directory:

```text
skills/
  chisel/
    SKILL.md
    references/
      ...
```

`SKILL.md` is the portable source file. Its markdown body describes the skill once.
Its YAML frontmatter contains a portable superset of metadata that adapters can
project into each harness.

```yaml
---
name: chisel
description: Edit file contents safely.
license: MIT
compatibility: Works in markdown-based coding harnesses.
allowed-tools:
  - read
  - edit
  - bash
metadata:
  owner: cheese-flow
  category: editing
harness:
  claude-code:
    allowed-tools:
      - Read
      - Edit
      - Bash(sd:*)
  cursor:
    globs:
      - "**/*"
    alwaysApply: false
---
```

## Portable Fields

Portable fields should mean the same thing regardless of target harness:

- `name` is the stable kebab-case skill identifier and must match the directory name.
- `description` is the short human-readable purpose.
- `license` records reuse terms when the source skill needs them.
- `compatibility` explains where the skill can run.
- `allowed-tools` describes the broad tool intent in source form.
- `metadata` carries repository-owned details that may not be emitted everywhere.

Adapters may preserve, transform, or omit these fields depending on the target
harness.

## Harness Overrides

Use `harness` only when a target needs different metadata from the portable default.
This keeps one canonical skill body while allowing valid per-harness output.

Examples:

- Claude Code can preserve Agent Skills frontmatter such as `allowed-tools`.
- Cursor may convert the same skill body into `.cursor/rules/*.mdc` and
  `.cursor/commands/*.md`, using fields like `description`, `globs`, and
  `alwaysApply`.
- A harness without hooks or tool restrictions should omit unsupported fields rather
  than emitting invalid metadata.

The rule is: validate generously at the source, emit strictly per target.

## Compiler Responsibilities

The compiler should:

1. Parse `skills/<name>/SKILL.md`.
2. Validate the portable source schema.
3. Check that `frontmatter.name` matches `<name>`.
4. Select the target harness adapter.
5. Emit only fields valid for that harness.
6. Copy references and other skill-local assets as needed.

Adapters own the projection from portable source to target output. The source skill
should not need to know each target filesystem layout.

## Where New Work Goes

- Add or update skill content in top-level `skills/`.
- Add source schema support in `src/lib/schemas.ts`.
- Add target-specific projection in `src/adapters/*`.
- Add compiler orchestration in `src/lib/compiler.ts` only when the pipeline itself
  needs to change.
