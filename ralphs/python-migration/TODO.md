# Python Migration — Stack Drivetrain

Each unchecked line below is one Graphite-stacked PR. Tick the box only when the story's
acceptance criteria in `.claude/specs/python-migration.md` are fully met.

The order encodes dependencies. Do not skip ahead — US-008 (installer.ts) depends on
US-005 (install-plan), US-006 (harness-detection), and US-007 (harness-compat).

- [x] US-001 — Package skeleton: rename pyproject to `cheese-flow`, add deps (typer, jinja2, pydantic>=2, ruamel.yaml), create `python/cheese_flow/{__init__,lib/__init__,adapters/__init__}.py`, declare `[project.scripts] cheese = "cheese_flow.cli:app"` placeholder, verify the correct `mcp` SDK version on PyPI before pinning
- [x] US-002 — Port `src/lib/schemas.ts` → `python/cheese_flow/lib/schemas.py` (Pydantic v2, `extra="forbid"`, all 9 schemas + discriminated unions); port matching vitest cases verbatim
- [x] US-003 — Port `src/adapters/{claude-code,codex,cursor,copilot-cli,_shared,index}.ts` → `python/cheese_flow/adapters/`; preserve registry shape; port adapter vitest cases
- [x] US-004 — Port compile pipeline: `compiler.ts` + `emit.ts` + `frontmatter.ts` + `capabilities.ts` + `model-manifest.ts` → `python/cheese_flow/lib/`; Eta `<%= %>` / `<% %>` → Jinja2 `{{ }}` / `{% %}`; `Promise.all` → `asyncio.gather`; commit a byte-parity snapshot fixture for one agent + one skill
- [x] US-005 — Port `src/lib/install-plan.ts` → `python/cheese_flow/lib/install_plan.py`; port `tests/install-plan.test.ts`
- [x] US-006 — Port `src/lib/harness-detection.ts` → `python/cheese_flow/lib/harness_detection.py`; port `tests/harness-detection.test.ts`
- [x] US-007 — Port `src/lib/harness-compat.ts` → `python/cheese_flow/lib/harness_compat.py`; port `tests/harness-compat.test.ts`
- [x] US-008 — Port `src/lib/installer.ts` → `python/cheese_flow/lib/installer.py`; depends on US-005/006/007; port `tests/installer.test.ts`
- [x] US-009 — Port `src/lib/sweeper.ts` → `python/cheese_flow/lib/sweeper.py`; port `tests/sweeper.test.ts`
- [x] US-010 — Port `src/lib/session-start.ts` → `python/cheese_flow/lib/session_start.py`; port `tests/session-start.test.ts`
- [x] US-011 — Port `src/lib/doctor.ts` → `python/cheese_flow/lib/doctor.py`; port matching vitest cases
- [x] US-012 — Port `src/lib/cheese-home.ts` → `python/cheese_flow/lib/cheese_home.py`; port `tests/cheese-home.test.ts`
- [x] US-013 — Port `src/lib/local-marketplaces.ts` → `python/cheese_flow/lib/local_marketplaces.py`; port matching vitest cases
- [ ] US-014 — Port lint pipeline: `src/lib/lint-skills.ts` + `lint-skill-rules.ts` → `python/cheese_flow/lib/`; port `tests/lint-skills-directory.test.ts` + `tests/lint-skill-source.test.ts`
- [ ] US-015 — FastMCP umbrella + Typer CLI: `python/cheese_flow/cli.py` (typer app, 7 subcommands, milknado top-level aliases) + `python/cheese_flow/mcp_server.py` (single FastMCP, `cheese_*` and `milknado_*` prefixed tools, stdio); deletes `src/lib/mcp-proxy.ts`; smoke-test that `cheese mcp tools/list` returns both prefix sets
- [ ] US-016 — Port any remaining `tests/*.test.ts` files not absorbed by earlier stories to `tests/python/test_*.py`
- [ ] US-017 — Cutover: delete `src/`, `tests/*.test.ts`, `package.json`, `package-lock.json`, `tsconfig*.json`, `biome.json`, `vitest.config.ts`; rewrite `justfile` (drop all `npm` recipes, uv-only `build`); update `.mcp.json` (`npx tsx ...` → `uv run cheese mcp`); update `hooks/cheese-bootstrap.sh`, `AGENTS.md`, `README.md`, `CLAUDE.md`, CI workflows; verify the MCP smoke test from `cheese mcp` and the byte-parity snapshot from US-004 still pass
