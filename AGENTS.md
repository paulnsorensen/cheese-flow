# cheese-flow — Agent Instructions

## Build Gate

**Run `just build` before opening any PR.** It must pass cleanly.

```
just build   # full autofix + lint + Python tests
```

If `just build` is red, do not open a PR. Fix failing tests or coverage gaps first.
Lint and format errors are auto-fixed by `just build` — re-run after if files changed.

## Recipes

```bash
just install     # Install all dependencies (uv)
just build       # Full pipeline with autofix — use this before every PR
just build-ci    # Full pipeline no autofix — CI uses this
just test        # Run pytest (passthrough: just test -k pattern)
just clean       # Remove build artifacts and caches
```

For anything else, call the underlying tool directly (`uv run cheese ...`, `uv run --group dev ...`).

## Required host tools

- **uv** — Python toolchain for the `cheese` CLI and `python/` checks.
- **`sg` (ast-grep)** — invoked from agent prompts (e.g. `nih-scanner`) for AST-shape patterns the tilth MCP doesn't cover. Install with `brew install ast-grep` or `cargo install ast-grep`.

## Project Overview

cheese-flow is a composition installer for the cheese ecosystem: it installs and verifies `hallouminate`, `easy-cheese`, and `tilth` across Claude Code, Codex, and Cursor, driven by a declarative TOML manifest.

- **Entry points**: `cheese` CLI (`python/cheese_flow/cli.py`)
- **Architecture**: Sliced Bread — flat modules under `python/cheese_flow/` plus component adapters under `python/cheese_flow/adapters/`
- **Templates**: Eta-rendered `agents/*.md.eta` and `skills/*/SKILL.md`
- **Tests**: `tests/python/` (pytest)

## Code Style

- Python 3.11+, formatted with ruff (line length 100)
- Max function: 40 lines, max file: 300 lines, max params: 4
- snake_case functions, PascalCase classes, SCREAMING_SNAKE_CASE constants, kebab-case files

## Engineering Principles

1. Trust nothing from external sources (validate at boundaries — pydantic for object safety)
2. Fail fast and loud — no silent failures
3. Separate business logic from infrastructure
4. YAGNI — only what's needed now
5. Name things after business concepts, not technical abstractions
6. Minimize state mutation

## No Migration Code

This project is pre-release. Do not add migration backfills, deprecation shims, or compatibility layers.
