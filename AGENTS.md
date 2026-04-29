# cheese-flow — Agent Instructions

## Build Gate

**Run `just build` before opening any PR.** It must pass cleanly.

```
just build   # full autofix + build + coverage + Python checks/tests
```

If `just build` is red, do not open a PR. Fix failing tests or coverage gaps first.
Lint and format errors are auto-fixed by `just build` — re-run after if files changed.

## Recipes

```bash
just install     # Install all dependencies (npm + uv)
just build       # Full pipeline with autofix — use this before every PR
just build-ci    # Full pipeline no autofix — CI uses this
just test        # Run vitest (passthrough: just test -t pattern)
just test-py     # Run pytest (passthrough: just test-py -k pattern)
just clean       # Remove build artifacts and caches
```

For anything else, call the underlying tool directly (`npx tsx src/index.ts ...`, `npm run <script>`, `uv run ...`).

## Project Overview

cheese-flow is opinionated scaffolding for portable agents and skills that compile into harness-specific markdown bundles (Claude Code, Codex, Cursor, Copilot CLI).

- **Entry points**: `cheese` CLI (`src/index.ts`), milknado Python TUI (`python/`)
- **Architecture**: Sliced Bread — vertical slices under `src/lib/` and `src/adapters/`
- **Templates**: Eta-rendered `agents/*.md.eta` and `skills/*/SKILL.md`
- **Tests**: `tests/` (vitest, coverage thresholds in `vitest.config.ts`) and `tests/python/` (pytest)

## Code Style

- TypeScript (Node 22+), formatted with Biome (`biome.json`)
- Python 3.11+, formatted with ruff (line length 100)
- Max function: 40 lines, max file: 300 lines, max params: 4
- camelCase functions (TS) / snake_case (Python), PascalCase classes, SCREAMING_SNAKE_CASE constants, kebab-case files

## Engineering Principles

1. Trust nothing from external sources (validate at boundaries — Zod for TS object safety)
2. Fail fast and loud — no silent failures
3. Separate business logic from infrastructure
4. YAGNI — only what's needed now
5. Name things after business concepts, not technical abstractions
6. Minimize state mutation

## Self-Refinement: producer-critic isolation

cheese-flow's iterative refinement model is grounded in two papers:

- **Self-Refine** (Madaan et al., 2023, [arxiv 2303.17651](https://arxiv.org/abs/2303.17651)) — single-LLM
  generator/refiner/feedback-provider loop. Cited here as the *anti-pattern motivation*: same-context
  self-critique is provably self-biased (Xu et al., ACL 2024) and amplifies that bias across iterations.
- **Reflexion** (Shinn et al., 2023, [arxiv 2303.11366](https://arxiv.org/abs/2303.11366)) — distinct
  Actor / Evaluator / Self-Reflection roles, raw trajectory dropped between attempts, distilled verbal
  lesson persisted in a bounded memory buffer. This IS the target pattern: isolation by prompt boundary,
  persistence by distilled lesson.

The cheese-flow embodiment is **fresh-context per-charter critics** — one critic per producer charter
(cook-critic, culture-critic, …), each dispatched as a fresh-window subagent that receives only an
artifact handle and re-derives findings from primary sources. This avoids embedding self-critique
inside the producer (Self-Refine self-bias trap) and avoids a single generic shared critic (loses
rubric specificity). See `skills/critique/SKILL.md` for the dispatch primitive.

## No Migration Code

This project is pre-release. Do not add migration backfills, deprecation shims, or compatibility layers.
