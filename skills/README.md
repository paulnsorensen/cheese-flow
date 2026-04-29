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
    SKILL.md          # the crust — public API, loaded by every harness
    scripts/          # executable helpers, invoked from SKILL.md only
      ...
    references/       # overflow prose, linked from SKILL.md only
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

## Sliced Bread Organization

Each skill directory is a **vertical slice**. The same crust/internals discipline that
applies to source code under `src/` (see [references/sliced-bread.md](../references/sliced-bread.md))
applies here, with the skill domain mapping as follows:

| Sliced Bread role | In `skills/<name>/` | Loaded by |
|---|---|---|
| Crust (public API) | `SKILL.md` | every harness directly |
| Internal implementation | `scripts/`, `references/`, any other subfolder | only the parent `SKILL.md` |
| Shared kernel | none yet — there is no `skills/common/` slice | n/a |

### The crust rule

`SKILL.md` is the ONLY contract a harness loader, an agent, or another skill is
allowed to depend on. Internals (`scripts/foo.py`, `references/bar.md`) are
implementation details — they can be renamed, split, or deleted without breaking
external callers.

```text
# BAD — reaching past the crust into another skill's internals
"run skills/merge-resolve/scripts/batch-resolve.py --apply" (from another-skill/SKILL.md)

# GOOD — delegate to the crust; the target skill decides how to do its job
"delegate to merge-resolve" (the calling skill picks merge-resolve up by name and
the target's SKILL.md owns how the work is performed)
```

The agents/skill loader follows the same rule: a sub-agent's `skills: [merge-resolve]`
attaches the crust; the agent never names a path under `scripts/`.

### Growth pattern

Start with a single `SKILL.md`. Add structure only when the file pushes back:

1. **One `SKILL.md`** — every skill begins here. Frontmatter + protocol body.
2. **Extract `scripts/`** when bash blocks repeat, exceed ~10 lines, or need
   value-equality test coverage. The Python tooling rules from `AGENTS.md`
   apply: stdlib-only when feasible, ruff-formatted, max-40-line functions,
   pytest in `tests/python/skills/<name>/`.
3. **Extract `references/`** when prose overflows the 500-line `SKILL.md`
   warning the linter emits. References are reading material, not code —
   keep procedure in `SKILL.md`, examples and rationale in references.
4. **Stay in `SKILL.md`** until either trigger fires. A six-line script
   inlined as a fenced bash block is fine; do not pre-create `scripts/`.

Concrete example: `merge-resolve` grew `scripts/` because four conflict-resolution
flows (`conflict-summary`, `batch-resolve`, `conflict-pick`, `lockfile-resolve`)
each needed multi-step Python with deterministic exit codes. `cheez-read`,
`cheez-write`, `cheez-search`, `gh`, and `research` are all single `SKILL.md`
files because nothing has crowded them out yet.

### Anti-patterns

- **Premature `scripts/`** — creating `skills/foo/scripts/` for a single 3-line
  bash invocation. Inline it until pressure forces extraction.
- **Cross-skill internal imports** — one skill's body referencing another skill's
  `scripts/` or `references/` directly. Always delegate via the crust.
- **Helper code in `SKILL.md`** — Python or bash that needs unit tests does not
  belong in fenced markdown blocks. Move to `scripts/` and add tests.
- **`references/` as a dumping ground** — references are markdown, scoped to a
  single topic, named for what they explain. They are not "stuff that wouldn't
  fit elsewhere".

### Cross-harness contract

Skills are the **only** isomorphic surface across all four target harnesses
(Claude Code, Codex, Copilot CLI, Cursor). The Sliced Bread crust matters more
here than for agents:

- Harness adapters copy `SKILL.md` plus `scripts/` and `references/` as opaque
  assets. They do not parse internals.
- A skill that depends on another skill must do so through the **name** in its
  frontmatter `compatibility:` or via documented delegation in the body — never
  via a hardcoded path that includes `scripts/` or `references/`.
- When `just build` wipes the per-harness output directories
  (`.claude/`, `.codex/`, `.cursor/`, `.copilot/`), the crust + internals get
  re-emitted as a unit. The source `skills/` tree is the durable record.

## Portable Fields

A field is portable when every harness adapter declares it in its `capabilities`
block. Fields not declared by any adapter are implicitly portable — they are
part of the universal source schema. Fields declared by only some adapters will
be silently dropped at compile time for adapters that do not declare them; the
`cheese lint` portability check surfaces a `frontmatter-portability` warning so
authors know to re-state the constraint in the skill body if other harnesses
also need to honor it.

Universal (implicitly portable) skill fields:

- `name` is the stable kebab-case skill identifier and must match the directory name.
- `description` is the short human-readable purpose.
- `license` records reuse terms when the source skill needs them.
- `compatibility` explains where the skill can run.
- `allowed-tools` describes the broad tool intent in source form. Use bare tool
  names (`Bash`, `Read`) for portability — Claude Code's permission-glob syntax
  (`Bash(git diff:*)`) is not parsed by Cursor, Codex, or Copilot CLI.
- `metadata` carries repository-owned details that may not be emitted everywhere.

Currently declared only by the `claude-code` adapter (will trigger a
`frontmatter-portability` warning on other harnesses):

- `model` — an optional model hint (e.g. `opus`, `haiku`); each adapter resolves
  it to a concrete identifier or drops it.
- `context` — `fork` or `inline`. `fork` asks the host to run the skill in a
  forked sub-agent context (Claude Code's `Agent` tool). Codex, Cursor, and
  Copilot CLI run the skill body inline regardless, so the body must still
  produce useful output without the fork. `inline` is the portable default and
  does not trigger a warning.

Adapters may preserve, transform, or omit fields depending on the target
harness. Adding a new adapter that supports `model` or `context` means editing
that adapter's `capabilities` declaration — no changes to the schema or lint
constants needed.

## Agent Portable Fields

Agent templates (`agents/*.md.eta`) share most of the skill model but live in a
separate domain. Each adapter ships a single rendered `<adapter-root>/agents/<name>.md`
per template; the frontmatter contract is:

| Field | Required | Adapters that emit it | Notes |
|---|---|---|---|
| `name` | yes | all | kebab-case slug, must be globally unique |
| `description` | yes | all | one-line summary surfaced in agent menus |
| `models` | yes | all (resolved) | per-harness identifiers; `default` is the fallback |
| `tools` | optional (defaults to `[]`) | all | bare tool names; permission-glob syntax is Claude-Code-only |
| `skills` | optional | `claude-code` adapter only | sub-agent skill bindings; non-Claude harnesses ignore the field |
| `color` | optional | `claude-code` adapter only | UI hint for `/agents` listings; ignored elsewhere |
| `effort` | optional (`low` / `medium` / `high`) | `claude-code` adapter only | run-budget hint; ignored elsewhere |
| `disallowedTools` | optional | `claude-code` adapter only | structural block-list; non-Claude harnesses fall back to the prompt contract |
| `permissionMode` | optional (`plan` / `acceptEdits` / `default`) | `claude-code` adapter only | dispatch-time permission hint |
| `metadata` | optional | repository-only | not emitted to any harness; useful for CI/lint analytics |

Fields listed as "`claude-code` adapter only" are currently declared in
`src/adapters/claude-code.ts`'s `capabilities.agentFrontmatterKeys`. The
`cheese lint` portability check surfaces a `frontmatter-portability` warning
when an author sets one of these fields; the constraint must be re-stated in the
prompt body if non-Claude harnesses also need to honor it. Adding adapter support
for a field means editing the relevant adapter's `capabilities` declaration.

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

## Linting

Skills are linted against the [Agent Skills format](https://agentskills.io/specification):

```bash
npm run lint:skills
# or
npx tsx src/index.ts lint
```

The linter enforces:

- A `SKILL.md` exists in every skill directory.
- Frontmatter is valid YAML and parses against the portable schema.
- `name` is kebab-case, 1-64 chars, with no leading/trailing/consecutive hyphens,
  and matches the parent directory name.
- `description` is 1-1024 characters (warns if shorter than 20).
- `compatibility`, when present, is at most 500 characters.
- `context`, when present, is `fork` or `inline`. `context: fork` warns that
  the hint is Claude-only and other harnesses will run the body inline.
- `allowed-tools` entries warn when they use Claude permission-glob syntax
  (`Tool(arg:*)`); strip the suffix to keep tool names portable.
- `SKILL.md` body warns when it references Claude-only tools (`Agent(...)`,
  `Task(...)`, `NotebookEdit`, `WebSearch`, `WebFetch`, `TodoWrite`),
  PascalCase hook events (`SessionStart`, `Stop`, `SubagentStop`,
  `Notification`, `PreCompact`, `UserPromptSubmit`, etc.), or
  harness-specific path markers (`.claude/`, `.codex/`, `.cursor/`,
  `.copilot/`, `AGENTS.md`, `copilot-instructions.md`).
- Frontmatter fields that are Claude-Code-only (`model` and `context` on
  skills; `skills` / `color` / `effort` / `disallowedTools` /
  `permissionMode` on agents) raise a `frontmatter-claude-only-field`
  warning so authors know non-Claude harnesses will drop them.
- `SKILL.md` body is at most 500 lines (warning); move overflow into `references/`.
- Each warning is anchored to a `file:line` in the report when the violation
  is body-resident, so editors can jump straight to the offending line.
- The compile-trip step exercises every adapter (`claude-code`, `codex`,
  `cursor`, `copilot-cli`) by simulating its install path against a tmp
  copy of the skill — adapter-specific failures surface as `compile-<harness>-failed`
  errors.
