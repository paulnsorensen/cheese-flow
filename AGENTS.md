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

## Pinned uv installer

`bootstrap.sh` is the `curl … | sh` entry point, and the uv installer it downloads is the
only code it runs that is not ours. It is pinned by version **and** SHA-256, and refuses to
execute a body that does not match.

Refresh the pin as part of cutting a release, so a fresh install never provisions a uv that
is many releases stale:

```bash
UV_VERSION=$(curl -fsSL https://api.github.com/repos/astral-sh/uv/releases/latest | jq -r .tag_name)
curl -fsSL --proto '=https' --tlsv1.2 "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh
sha256sum /tmp/uv-install.sh
```

Set `UV_VERSION` and `UV_INSTALLER_SHA256` in `bootstrap.sh` to those two values, then run
`just build`.

Two rules for anyone touching this:

1. **Keep the version in the URL.** Astral serves the unversioned `/uv/install.sh` from
   whatever release is current, so a hash pinned against it breaks for every user on every
   uv release. Only `/uv/<version>/install.sh` is frozen.
2. **Never add an environment variable that skips verification.** A bypass knob is exactly
   the hole the pin exists to close. Tests that need their own installer accepted rewrite
   the constant in a copy of the script instead.

A hash mismatch against a frozen versioned URL means the content changed underneath a
release that should be immutable. Treat that as a supply-chain incident, not a stale pin.

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
