---
applyTo: "**"
excludeAgent: "cloud-agent"
---

## Code Review Focus

Focus reviews on these categories, in priority order:

1. **Supply chain & security** - Flag hardcoded secrets, command injection (this tool shells out to harness CLIs), path traversal, unpinned or verification-weakened downloads, and any change that loosens the `bootstrap.sh` uv-installer pin (scoped in `bootstrap.instructions.md`). This installer writes into users' home directories — treat every write path and every fetched artifact as hostile until validated.
2. **Silent failures** - Flag swallowed exceptions, empty `except` blocks, or install/apply steps that report success without verifying their effect. A half-applied profile must surface, not vanish.
3. **Coupling violations** - Flag harness- or component-specific behavior inlined into planning, models, or CLI code instead of an adapter under `python/cheese_flow/adapters/`.
4. **Complexity violations** - Flag functions over 40 lines, files over 300 lines, functions with more than 4 parameters, nesting deeper than 3 levels. Do not flag a file that is already over budget on `main` unless the diff makes it larger.
5. **Architectural violations** - Flag cross-module internal reaches, mutable shared state, God modules, and single-use abstractions (factories, registries, ABCs with one implementation).

Test quality rules are scoped to `tests/**` in `tests.instructions.md`; shell rules to `**/*.sh` in `shell.instructions.md`; the bootstrap supply-chain contract to `bootstrap.instructions.md` — do not duplicate those categories here.

## What NOT to Comment On

- Linting, formatting, and import ordering — handled by Ruff (E, F, I, UP, B, SIM) in `just build` / `just build-ci`
- Missing docstrings on internal or private functions
- Style preferences that are consistent with the rest of the codebase
- Nitpicks with no functional impact

## Review Style

- Only comment when confidence is high
- If a pattern is used consistently elsewhere in the codebase, do not flag it as wrong
- Suggest specific fixes, not vague improvements
- One comment per issue — do not repeat the same feedback on multiple occurrences
