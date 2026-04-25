# cheese-flow

Opinionated scaffolding for portable agents and skills that can be compiled into harness-specific markdown bundles.

## Stack choices

- **CLI framework:** Commander.js, the most practical general-purpose TypeScript CLI choice for April 2026
- **Object safety:** Zod
- **Template engine:** Eta for portable template-to-markdown compilation
- **Skill format:** Agent Skills compatible `SKILL.md`

## Repository layout

- `src/` — TypeScript CLI and compiler
- `agents/` — harness-agnostic Eta markdown templates
- `skills/` — portable Agent Skills definitions
- `references/` — long-form architectural references (Sliced Bread, etc.)
- `.claude-plugin/` — Claude Code + Copilot CLI install manifest
- `.cursor-plugin/` — Cursor install manifest
- `.mcp.json` — shared MCP server declarations (tilth, Context7, Tavily)
- `.claude/` / `.codex/` / `.cursor/` / `.copilot/` — generated install outputs (gitignored)

## Getting started

```bash
npm install
npm run build
npm run install:claude
npm run install:codex
npm run install:cursor
npm run install:copilot
```

Or use the repository automation entrypoints:

```bash
just build
just build-ci
```

Or target specific harnesses directly:

```bash
npx tsx src/index.ts install --harness claude-code
npx tsx src/index.ts install --harness codex
npx tsx src/index.ts install --harness cursor
npx tsx src/index.ts install --harness copilot-cli
npx tsx src/index.ts install --harness claude-code,codex,cursor,copilot-cli
npx tsx src/index.ts milknado
```

## Installing cheese-flow as a plugin

Teammates can install directly from the repo via their harness's native plugin command:

```
# Claude Code
/plugin install paulnsorensen/cheese-flow

# Copilot CLI
copilot plugin install paulnsorensen/cheese-flow

# Cursor
# Configure via .cursor/settings.json pointing at this repo (see Cursor plugin docs)
```

Once the package is built or published, the same TUI demo is available through:

```bash
npx cheese-flow milknado
```

## What `install` does

- Validates Agent Skills frontmatter with Zod
- Validates agent template metadata with Zod
- Compiles `agents/*.md.eta` into plain markdown for the selected harness
- Copies `skills/*/SKILL.md` into the harness bundle
- Writes a small manifest for the generated bundle

## `milknado`

- Runs a Python backend through `uv run --project ...`
- Streams the Rich-rendered terminal UI to stdout/stderr
- Uses OR-Tools to solve and display a small linear optimization result
- Requires `uv` on `PATH`

## Quality gates

- `just build` installs deps, formats, lints with autofix, typechecks, builds, and runs tests with coverage thresholds
- `just build-ci` uses the same checks without autofix and is what CI runs
- Vitest coverage thresholds are set above 90% for statements, branches, functions, and lines

## Example output

- Claude Code bundle: `.claude/`
- Codex bundle: `.codex/`
- Cursor bundle: `.cursor/`
- Copilot CLI bundle: `.copilot/`

Each bundle contains:

- `agents/*.md`
- `skills/*/SKILL.md` (Cursor: `rules/<skill>.mdc` + `commands/<skill>.md` dual-surface)
- `manifest.json`
- `.mcp.json` (Cursor: `mcp.json`)
- Per-harness plugin manifest (`.claude-plugin/`, `.cursor-plugin/`, or `.codex-plugin/`)
- `hooks.json` (except Cursor, which does not support hooks)

## References

Long-form architectural docs live under `references/`. Currently:

- [`references/sliced-bread.md`](./references/sliced-bread.md) — language-agnostic Sliced Bread architecture (vertical slices, organic growth, boundary rules).
- [`references/sb/practice.md`](./references/sb/practice.md) — applied patterns (CQRS, anti-corruption layers, testing, slice-local duplication, slice graduation to packages/libraries/services).
- [`references/sb/attribution.md`](./references/sb/attribution.md) — predecessor lineage (VSA, Hexagonal, Screaming, Clean, Onion, DDD).
- [`references/sb/rust.md`](./references/sb/rust.md) — Rust-specific guide (module privacy, `foo.rs` + `foo/` facade).
- [`references/sb/go.md`](./references/sb/go.md) — Go-specific guide (`internal/` packages, `go.work`).
- [`references/sb/ts.md`](./references/sb/ts.md) — TypeScript-specific guide (`exports` maps, why barrel files are now anti-pattern).

These are reference material only — not yet wired into any skill or agent.