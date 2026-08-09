---
applyTo: "**"
excludeAgent: "code-review"
---

## Coding Agent Guidelines

When implementing changes:

- Read existing code before modifying it — understand the patterns in use
- Follow the existing code style of the file you are editing
- Keep changes minimal and focused on the issue at hand
- Do not refactor surrounding code unless the issue requires it
- Do not add docstrings to helper functions or private methods with clear names
- Do not introduce new dependencies without explicit approval; manage everything through `uv`
- Write tests for new functionality — match the existing pytest / pytest-bdd patterns in `tests/python/`
- Prefer editing existing files over creating new ones
- Run `just build` before opening a PR — it must pass cleanly (autofix + lint + tests); re-run if autofix changed files

## Architecture Rules

- Harness- and component-specific behavior goes in an adapter under `python/cheese_flow/adapters/`, never inlined into planning or CLI code
- Validate external input (manifest TOML, harness config, CLI args) with pydantic models at the boundary
- No migration code — this project is pre-release; change the code directly instead of adding backfills, deprecation shims, or compatibility layers
- Never touch the `bootstrap.sh` uv-installer pin except through the release refresh procedure in `AGENTS.md`, and never add a verification bypass
