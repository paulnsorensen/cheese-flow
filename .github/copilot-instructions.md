# Copilot Instructions

## Engineering Principles

1. **Input Validation** - Trust nothing from external sources. Validate at system boundaries (manifest TOML, harness config files, CLI arguments, downloaded artifacts) — pydantic models for object safety. Internal code trusts internal code.
2. **Fail Fast and Loud** - Handle errors where they occur. No silent failures, no swallowed exceptions, no empty defaults on error. An installer that half-succeeds silently is worse than one that stops loudly.
3. **Loose Coupling** - Separate business logic from infrastructure. Core models and planning logic must not shell out, touch the network, or depend on a specific harness; harness- and component-specific behavior lives in `python/cheese_flow/adapters/`.
4. **YAGNI** - Build only what is needed now. No abstract base classes with one implementation, no config options that are never varied.
5. **Real-World Models** - Name things after installer concepts: `DesiredState`, `Harness`, `Profile`, `Repository` — not `DataProcessor`, `Manager`, `StrategyHandler`.
6. **Immutable Patterns** - Minimize state mutation. Prefer pure functions and returning new values over mutating arguments.

## Complexity Budget

- **Functions**: Maximum 40 lines
- **Files**: Maximum 300 lines
- **Parameters**: Maximum 4 per function
- **Nesting**: Maximum 3 levels deep

If a function or file exceeds these limits, decompose it.

## Code Style

- **Classes**: PascalCase
- **Functions / variables**: snake_case
- **Constants**: SCREAMING_SNAKE_CASE
- **Files**: kebab-case (snake_case for Python modules, matching the existing tree)
- **Commits**: Conventional Commits format (`feat:`, `fix:`, `chore:`, etc.)

## Architecture

Follow the Sliced Bread layout:

- Flat concept modules under `python/cheese_flow/` (`cli`, `install`, `desired_state`, `models`, `repositories`, `runner`, `doctor`, `harness_detection`, `tui`) with component adapters under `python/cheese_flow/adapters/` and profile logic under `python/cheese_flow/profiles/`.
- Harness- and component-specific behavior belongs in an adapter, never inlined into planning or CLI code.
- Templates are Eta-rendered `agents/*.md.eta` and `skills/*/SKILL.md`; generated harness config is data, not code.
- One-directional dependencies only; do not reach into another module's internals.

## No Migration Code

This project is pre-release. Do not add migration backfills, deprecation shims, or compatibility layers.

## What NOT to Do

- Do not add docstrings to private methods or small helpers with clear names.
- Do not create abstract base classes, factories, or registries unless there are 2+ concrete implementations today.
- Do not add error handling for conditions that cannot occur in the current system.
- Do not add backwards-compatibility shims — change the code directly.
- Do not wrap functions that add no logic — call the original directly.
- Do not add type annotations to every local variable — annotate function signatures and let inference handle the rest.
- Never weaken the `bootstrap.sh` uv-installer pin or add a verification bypass (see `bootstrap.instructions.md`).

## Tech Stack

- **Language**: Python 3.11+ (`uv` for all dependency and environment management; package root `python/cheese_flow/`)
- **Boundary models**: pydantic v2
- **CLI**: typer + rich
- **Config**: tomlkit (manifest), PyYAML
- **Tests**: pytest + pytest-bdd (features under `tests/python/features/`), smoke install via `just smoke`
- **Lint**: Ruff (E, F, I, UP, B, SIM; line length 100)
- **Shell**: `bootstrap.sh` curl-pipe entry point and repo hooks

## Build, Test, and Lint Commands

- **The PR gate**: `just build` — autofix format + lint, then pytest. Must pass before any PR; CI runs `just build-ci` (no autofix).
- Tests: `just test` (passthrough: `just test -k pattern`)
- Smoke install into a throwaway HOME: `just smoke [harness]`
- Install deps: `just install`
