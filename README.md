# 🧀 cheese-flow 🧀

> _"The cheese must flow."_

Opinionated scaffolding for portable agents and skills that can be compiled into harness-specific markdown bundles. Aged in Python, served on Sliced Bread, paired nicely with Claude Code, Codex, Cursor, and Copilot. 🧀

## Why Cheese? Two reasons:

1. **Modeled after the gaming slang term "cheese."** The term traces back to early fighting-game culture in the late 1980s and early 1990s — Street Fighter II players coined "cheesy" wins to describe victories pulled off with cheap, repeatable, low-skill tactics (corner-trap fireball spam, throw loops, AI-pattern exploits). It spread from fighting games to RTS rush builds (StarCraft "cheese rushes"), to speedrun glitch routes, to MOBA cheese picks — anywhere a player gets a disproportionately good result for very little effort. That is exactly the design center of cheese-flow: the primary tenets are **correctness, token efficiency, and quality** — _cheap and easy_ in the best sense. Maximum result, minimum spend.
2. **What's life without whimsy?** 🧀

## Stack choices

- **CLI framework:** Typer — type-hint-driven Python CLIs that pair naturally with pydantic
- **Object safety:** pydantic v2
- **Template engine:** Jinja2 for portable template-to-markdown compilation
- **Skill format:** Agent Skills compatible `SKILL.md`
- **MCP server:** FastMCP — a single Python process exposes both `cheese_*` and `milknado_*` tools

## Repository layout

- `python/cheese_flow/` — Python CLI, compiler, and unified MCP server
- `python/milknado/` — sovereign milknado slice (graph + planning, OR-Tools)
- `agents/` — harness-agnostic Jinja2 markdown templates
- `skills/` — portable Agent Skills definitions
- `references/` — long-form architectural references (Sliced Bread, etc.)
- `.claude-plugin/` — Claude Code + Copilot CLI plugin manifest
- `.cursor-plugin/` — Cursor plugin manifest
- `.mcp.json` — shared MCP server declarations (cheese-flow, tilth, Context7, Tavily)
- `.claude/` / `.codex/` / `.cursor/` / `.copilot/` — generated harness bundles (gitignored)

## Getting started

Host prerequisites: `uv` and `sg` (ast-grep) on `PATH`. Install ast-grep
globally with `brew install ast-grep` or `cargo install ast-grep`.

```bash
uv sync --group dev

# Emit bundles for every harness
uv run cheese compile

# Install into whichever local harnesses are detected
uv run cheese install
```

Or use the repository automation entrypoints:

```bash
just build
just build-ci
```

Or target specific harnesses directly:

```bash
# Bundle emission
uv run cheese compile
uv run cheese compile --harness claude-code,copilot-cli
uv run cheese compile --harness claude-code,codex,cursor,copilot-cli

# Local installation (auto-detect by default)
uv run cheese install
uv run cheese install --harness cursor,copilot-cli
uv run cheese install --harness claude-code,codex

# Python demo
uv run cheese milknado
```

`cheese compile` emits harness bundles for repo authors and CI. `cheese install`
compiles the selected bundles and installs them into local harness surfaces,
auto-detecting installed harnesses unless you pass `--harness`.

## Installing compiled bundles locally

Point harness installers at the compiled bundle directories (`.claude/`,
`.codex/`, `.cursor/`, `.copilot/`) instead of the repository root.

| Harness | Compiled install surface | What `cheese install` does |
|---|---|---|
| Claude Code | `.claude/` | Compiles the bundle, writes local marketplace metadata, and prints `claude plugin marketplace add "<repo>/.claude"` plus the in-app install step. |
| Codex | `.codex/` | Compiles the bundle, writes local marketplace metadata, and prints `codex plugin marketplace add "<repo>/.codex"` plus the restart/install steps. |
| Cursor | `.cursor/` | Compiles `.cursor/`; that tree is already the installed surface. |
| Copilot CLI | `.copilot/` | Compiles `.copilot/` and runs `copilot plugin install "<repo>/.copilot"` when the CLI is available. |

Examples:

```bash
# Auto-detect installed harnesses and install only those
uv run cheese install

# Explicit multi-harness install
uv run cheese install --harness cursor,copilot-cli

# Bundle emission only, then manual bundle-surface install
uv run cheese compile --harness claude-code,codex
claude plugin marketplace add ./.claude
codex plugin marketplace add ./.codex
```

Once published to PyPI, install globally with:

```bash
uv tool install cheese-flow
cheese milknado
```

## What `compile` does

- Validates Agent Skills frontmatter with pydantic
- Validates agent template metadata with pydantic
- Compiles `agents/*.md.eta` into plain markdown for the selected harness
- Copies `skills/*/SKILL.md` into the harness bundle
- Writes a small manifest for the generated bundle

## `milknado`

- Runs the milknado Python backend in-process (same `cheese` interpreter)
- Streams the Rich-rendered terminal UI to stdout/stderr
- Uses OR-Tools to solve and display a small linear optimization result

## Quality gates

- `just build` installs deps, formats, lints with autofix, and runs the pytest suite
- `just build-ci` uses the same checks without autofix and is what CI runs

## Example bundle/install surfaces

- Claude Code bundle/install surface: `.claude/`
- Codex bundle/install surface: `.codex/`
- Cursor bundle/install surface: `.cursor/`
- Copilot CLI bundle/install surface: `.copilot/`

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
