# 🧀 cheese-flow 🧀

> _"The cheese must flow."_

A composition installer for the cheese ecosystem: it installs and verifies `hallouminate`, `easy-cheese`, and `tilth` across Claude Code, Codex, and Cursor, driven by a single declarative TOML manifest. Aged in Python, served on Sliced Bread. 🧀

## Why Cheese? Two reasons:

1. **Modeled after the gaming slang term "cheese."** The term traces back to early fighting-game culture in the late 1980s and early 1990s — Street Fighter II players coined "cheesy" wins to describe victories pulled off with cheap, repeatable, low-skill tactics (corner-trap fireball spam, throw loops, AI-pattern exploits). It spread from fighting games to RTS rush builds (StarCraft "cheese rushes"), to speedrun glitch routes, to MOBA cheese picks — anywhere a player gets a disproportionately good result for very little effort. That is exactly the design center of cheese-flow: the primary tenets are **correctness, token efficiency, and quality** — _cheap and easy_ in the best sense. Maximum result, minimum spend.
2. **What's life without whimsy?** 🧀

## Stack choices

- **CLI framework:** Typer — type-hint-driven Python CLIs that pair naturally with pydantic
- **Object safety:** pydantic v2
- **Manifest format:** TOML, parsed with the standard library `tomllib` and written atomically
- **Terminal UI:** Rich — drives both the interactive wizard and headless status output

## Repository layout

- `python/cheese_flow/` — the `cheese` CLI, profile engine, desired-state manifest handling, install planner, doctor, and the interactive wizard TUI
- `python/cheese_flow/adapters/` — one adapter per component (`hallouminate`, `easy-cheese`, `tilth`)
- `tests/python/` — pytest suite
- `agents/`, `skills/`, `commands/` — this repo's own agent-authoring assets (prompts, skills, slash commands), used to develop cheese-flow itself
- `references/` — long-form architectural references (Sliced Bread, etc.)
- `.claude-plugin/` / `.cursor-plugin/` — this repo's own Claude Code / Cursor plugin manifests
- `.mcp.json` — shared MCP server declarations (tilth, Context7, Tavily)
- `bootstrap.sh` — the curl-pipe-sh entry point: installs `uv` when absent, then runs `cheese install`

## Getting started

On a bare box — a cloud sandbox, a fresh VM, a container with nothing but curl, git, and node — one line does the whole install:

```bash
curl -fsSL https://raw.githubusercontent.com/paulnsorensen/cheese-flow/main/bootstrap.sh \
  | sh -s -- --harness claude-code
```

`bootstrap.sh` installs `uv` when it is absent and hands every argument after `--` to `cheese install`. Pass the state options: piping the script into `sh` consumes stdin, which is what the interactive wizard reads, so this path is headless by construction.

On a time-budgeted sandbox setup (e.g. Claude Code on the web's setup script, ~5-minute budget), append `--timeout 90` so a stuck child fails inside the budget instead of consuming the default 900s — it's a budget-derived floor, so raise it if a legitimate step (e.g. a cold `npm install -g` or the tilth nightly download) trips it.

Every `cheese` run bounds stalled git transfers via `GIT_HTTP_LOW_SPEED_LIMIT`/`GIT_HTTP_LOW_SPEED_TIME` (1000 B/s over 30s by default); caller-set values win.

The only host prerequisites are `curl` ≥ 7.71 (needed for `--retry-all-errors`), `git`, `tar`, a sha256 tool (`sha256sum` or `shasum`), and the `npm` toolchain the npm-based components install themselves with; `tilth` downloads its own binary. No GitHub CLI is needed. During the nightly republish window the tilth download can retry for up to ~2 min per file.

Registered harnesses launch `tilth` from `${XDG_BIN_HOME:-$HOME/.local/bin}`, so that directory must be on `PATH`.

### From a checkout

Host prerequisite: `uv` on `PATH`.

```bash
uv sync --group dev

# Interactive wizard install
uv run cheese install

# Verify already-declared managed state
uv run cheese doctor
```

### Agent profiles

Profile commands are explicit and machine-readable; every source-consuming command
requires an explicit source root:

```bash
uv run cheese profile list --source-root /path/to/dotfiles
uv run cheese profile describe global --source-root /path/to/dotfiles
uv run cheese profile compile global \
  --source-root /path/to/dotfiles \
  --baseline /path/to/baseline \
  --output /path/to/publication
uv run cheese profile apply /path/to/publication/manifest.json
uv run cheese profile launch claude global \
  --source-root /path/to/dotfiles -- --resume
uv run cheese profile permissions --project-root /path/to/project
```

`profile launch` validates the complete launch specification before replacing
the process. `profile permissions` renders the fixed project-local permission
fragment; pass `--local` for Claude's gitignored personal settings or repeat
`--harness` to select a subset.

Or use the repository automation entrypoints:

```bash
just build
just build-ci
```

No checkout needed — `uvx` runs the CLI straight from the repository:

```bash
# Interactive wizard
uvx --from git+https://github.com/paulnsorensen/cheese-flow cheese install

# Headless, no manifest file: declare the state on the command line
uvx --from git+https://github.com/paulnsorensen/cheese-flow cheese install \
  --harness "claude-code codex" --component hallouminate,easy-cheese --repo . --json
```

Append `@main` or `@<sha>` to the URL to pin a revision. `--from` is required either way: the package is `cheese-flow`, the command is `cheese`.

Once published to PyPI, install globally with:

```bash
uv tool install cheese-flow
cheese install
```

## Commands

### `cheese install`

Installs the selected components for the selected harnesses and repositories.

| Option | Effect |
|---|---|
| `--config PATH` | Apply this manifest headlessly instead of running the wizard |
| `--harness NAMES` | Harnesses to manage, comma- or space-separated. Repeatable. Runs headlessly |
| `--component NAMES` | Components to install, comma- or space-separated. Defaults to all of them |
| `--repo PATHS` | Repositories to index, comma- or space-separated. Relative paths are resolved. Each must be a git repository |
| `--write-config` | Persist the resolved manifest. Options are ephemeral without it |
| `--dry-run` | Emit the plan without changing managed state |
| `--json` | Write one JSON document to stdout (also runs headlessly) |
| `--timeout FLOAT` | Seconds a single command may run before it is killed |

With no `--config`/`--json` and no state options, `install` runs the interactive wizard and, on acceptance, persists the manifest to the default config path before applying it.

`--harness`/`--component`/`--repo` declare the desired state without a manifest file, which is the CI and cloud path — nothing is persisted unless you pass `--write-config`. Each selected repository's parent becomes its search root, and a `--repo` path that is not a git repository is rejected before anything is planned. Two combinations are rejected: `--config` with any state option (two sources of state), and `--write-config` with `--dry-run` (a dry run persists nothing).

### `cheese doctor`

Verifies declared managed state without changing it.

| Option | Effect |
|---|---|
| `--config PATH` | Manifest to verify. Defaults to the standard path |
| `--timeout FLOAT` | Seconds a single command may run before it is killed |

Both commands write a single JSON report to stdout in headless mode; every prompt, progress line, and diagnostic goes to stderr.

## The manifest

Default path: `$XDG_CONFIG_HOME/cheese/config.toml` (falls back to `~/.config/cheese/config.toml`).

```toml
harnesses = ["claude-code", "codex", "cursor"]
components = ["hallouminate", "easy-cheese", "tilth"]

[repositories]
search_roots = ["/home/you/Dev"]
max_depth = 2
selected = ["/home/you/Dev/some-repo"]
```

- **Harnesses:** `claude-code`, `codex`, `cursor`
- **Components:** `hallouminate`, `easy-cheese`, `tilth` — `hallouminate` and `easy-cheese` are required in every manifest; `tilth` is optional
- **Repositories:** `search_roots` are where repository discovery looks, `max_depth` bounds how deep it searches, and `selected` must each sit under one of the search roots

## Quality gates

- `just build` installs deps, formats, lints with autofix, and runs the pytest suite
- `just build-ci` uses the same checks without autofix and is what CI runs

## References

Long-form architectural docs live under `references/`. Currently:

- [`references/sliced-bread.md`](./references/sliced-bread.md) — language-agnostic Sliced Bread architecture (vertical slices, organic growth, boundary rules).
- [`references/sb/practice.md`](./references/sb/practice.md) — applied patterns (CQRS, anti-corruption layers, testing, slice-local duplication, slice graduation to packages/libraries/services).
- [`references/sb/attribution.md`](./references/sb/attribution.md) — predecessor lineage (VSA, Hexagonal, Screaming, Clean, Onion, DDD).
- [`references/sb/rust.md`](./references/sb/rust.md) — Rust-specific guide (module privacy, `foo.rs` + `foo/` facade).
- [`references/sb/go.md`](./references/sb/go.md) — Go-specific guide (`internal/` packages, `go.work`).
- [`references/sb/ts.md`](./references/sb/ts.md) — TypeScript-specific guide (`exports` maps, why barrel files are now anti-pattern).

These are reference material only — not yet wired into any skill or agent.
