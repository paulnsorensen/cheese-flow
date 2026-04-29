# Dotfiles Claude Takeover Inventory

Source reviewed: `/Users/paul/Dev/dotfiles/claude`

This inventory tracks Claude Code skills, commands, and agents that are worth
moving into `cheese-flow` as portable source material. It is intentionally a
triage document, not a migration log.

## Current Shape

- Dotfiles source contains 42 skill definitions, 34 slash commands, and 43 agent
  definitions across global and plugin-local directories.
- `cheese-flow` currently has the portable source model documented in
  `skills/README.md`, one starter skill, five commands, and one agent template.
- Best target for portable skill content is `skills/<name>/SKILL.md`.
- Best target for reusable command content is `commands/<name>.md`.
- Best target for agents is likely `agents/<name>.md.eta`, because agent metadata
  needs harness-specific projection.

## Priority 1: Bring Over First

These assets are broadly useful, mostly markdown-first, and have low coupling to
personal paths or Claude-only behavior.

### Skills

| Asset | Source | Why It Belongs |
| --- | --- | --- |
| `chisel` | `skills/chisel/SKILL.md` | Safe editing patterns and `sd` usage are broadly portable. |
| `commit` | `skills/commit/SKILL.md` | Focused staging and conventional commit discipline should travel across harnesses. |
| `de-slop` | `skills/de-slop/SKILL.md` | Core quality guard against predictable AI code smells. |
| `diff` | `skills/diff/SKILL.md` | Lightweight pre-commit smoke review. |
| `git-hygiene` | `skills/git-hygiene/SKILL.md` | Prevents unsafe git-content access patterns. |
| `justfile` | `skills/justfile/SKILL.md` | Practical project automation onboarding. |
| `lint` | `skills/lint/SKILL.md` | Multi-language lint routing and summarization. |
| `nih-audit` | `skills/nih-audit/SKILL.md` | Library-vs-custom-code audit is broadly useful. |
| `ralphify-spec` | `skills/ralphify-spec/SKILL.md` | Converts iterative work into repeatable loop specs. |
| `self-eval` | `skills/self-eval/SKILL.md` | Portable response/change quality checklist. |
| `skill-improver` | `skills/skill-improver/SKILL.md` | Directly supports maintaining this repo's skill catalog. |
| `tdd-assertions` | `skills/tdd-assertions/SKILL.md` | Strengthens tests across languages. |
| `tui-design` | `skills/tui-design/SKILL.md` | Mostly design guidance; low harness coupling. |
| `version-doctor` | `skills/version-doctor/SKILL.md` | Common dependency/version failure workflow. |
| `worktree` | `skills/worktree/SKILL.md` | General isolated-branch workflow. |

### Commands

| Asset | Source | Why It Belongs |
| --- | --- | --- |
| `init` | `plugins/local/cheese-flow/commands/init.md` | Already cheese-flow branded; should live in the repo as source of truth. |
| `explore` | `plugins/local/cheese-flow/commands/explore.md` | Core cheese-flow value proposition. |
| `hello` | `plugins/local/cheese-flow/commands/hello.md` | Cheap install smoke test. |
| `research` | `commands/research.md` | Thin wrapper around the `research` skill. |
| `diff` | `commands/diff.md` | Thin wrapper around the `diff` skill. |
| `respond` | `commands/respond.md` | Useful PR-review workflow once GitHub tooling is modeled. |
| `worktree` | `commands/worktree.md` | Thin wrapper around the `worktree` skill. |
| `pingpong` | `commands/pingpong.md` | Portable TDD pairing prompt. |
| `hint` | `commands/hint.md` | Portable teaching prompt; needs normalized frontmatter. |
| `explain` | `commands/explain.md` | Portable concept explanation workflow. |
| `duck` | `commands/duck.md` | Portable rubber-duck workflow. |
| `pull` | `commands/pull.md` | Useful in multi-worktree flows; validate assumptions before shipping. |

### Agents

| Asset | Source | Why It Belongs |
| --- | --- | --- |
| `cheese-factory` | `agents/cheese-factory.md` | General codebase orientation. |
| `ghostbuster` | `agents/ghostbuster.md` | Reusable dead-code/spec-drift forensic agent. |
| `nih-scanner` | `agents/nih-scanner.md` | Pairs with the `nih-audit` skill. |
| `lsp-probe` | `agents/lsp-probe.md` | Useful short-lived LSP query broker. |
| `explore-lsp` | `plugins/local/cheese-flow/agents/explore-lsp.md` | Low-coupling part of the cheese-flow exploration stack. |

## Priority 2: Adapt Before Porting

These are valuable, but they assume specific tools, Claude Code paths, MCP
servers, or sub-agent names. They should move after the compiler can express the
right harness overrides.

### Skills

- `fetch` and `research`: keep the routing ideas, but split Context7/Tavily
  and scratch-file details into harness-specific metadata.
- `make`: preserve build/test detection; isolate the Claude-specific "hooks block
  raw builds" behavior.
- `lookup`, `trace`, `scout`, `prek`, `merge-resolve`: useful but need explicit
  CLI availability assumptions.
- `gh` and `respond`: valuable once GitHub MCP vs `gh` fallback is represented
  cleanly.
- `ghostbuster`, `xray`, `spec-verify`, `age`: high value, but agent packs and
  spec paths need to be bundled consistently.
- `session-analytics`, `test-sandbox`: useful for Claude Code users, but personal
  paths such as `~/.claude` must not leak into default portable output.
- `init` and `explore` from the local cheese-flow plugin: should become
  first-class repo skills, but they depend on tilth, tokei, LSP, and graph tooling.

### Commands

- `age`: merge with the existing `commands/age.md`; do not duplicate.
- `code-review`, `spec`, `nih-audit`, `ghostbuster`, `skill-improver`,
  `setup-perms`, `scaffold`, `test`, `wreck`, `onboard`, `audit`, `simplifier`:
  useful workflows, but each needs path/tool normalization or bundled agents.
- `move-my-cheese`, `cheese-convoy`: treat as an optional platform bundle.
  They only make sense once the parallelism layer (planned as a milknado
  reboot) is back in cheese-flow.
- `copilot-review`, `copilot-delegate`, `copilot-setup`: keep optional until
  Copilot is intentionally supported as a first-class target.
- `agents`: rewrite to inspect project/compiled assets, not hardcoded
  `~/.claude` paths.

### Agents

- `whey-drainer`, `roquefort-wrecker`, `ricotta-reducer`: strong quality agents;
  adapt build/test commands and skill dependencies.
- `culture-*`, `worktree-triage`: wait until worktree, token-sizing, and MCP
  dependencies are explicit in `cheese-flow`.
- `explore-tilth`, `explore-tokei`, `explore-graph`: keep as optional exploration
  layers behind installed-tool or MCP checks.
- `xray` reference agents: useful as an opt-in bundle once the `xray` skill is
  adapted.

## Leave Local For Now

- `settings-clean`: valuable for a personal Claude Code setup, but not portable.
- `worktree-sweep`: tied to `ccw-sweep` and a personal `~/Dev` layout.
- `skill-analytics-*`: depends on personal Claude Code analytics data.
- `todoist-flow` skills and agents: separate product/plugin, not core
  `cheese-flow`.
- `hello-cheese`: scaffold/demo value only; superseded by `basic-skill` and real
  cheese-flow commands.
- `culture-context7`: wait until Context7 is a declared dependency.

## Open Decisions

1. Should `cheese-flow` ship one default bundle plus optional packs, or should all
   assets compile into every harness by default?
2. Should agents stay Claude-oriented, or should the source schema grow a portable
   agent metadata model with per-harness model/tool projections?
3. How should MCP-backed capabilities such as Context7, tilth, graph search, and
   GitHub be expressed: required dependency, optional feature, or harness override?
4. Where should Claude-only operational paths such as `.claude/specs`,
   `.claude/review`, and `~/.claude/analytics` be normalized for other harnesses?

## Suggested First Migration Batch

1. Copy the Priority 1 skills into `skills/`, adding portable frontmatter:
   `name`, `description`, `license`, `compatibility`, and broad `allowed-tools`.
2. Copy supporting `references/` and `scripts/` directories for skills that have
   local assets, especially `justfile`, `ralphify-spec`, `de-slop`, and
   `skill-improver`.
3. Bring over plugin-local `init`, `explore`, and `hello` commands with matching
   `init` and `explore` skills.
4. Add the first low-coupling agents: `cheese-factory`, `ghostbuster`,
   `nih-scanner`, `lsp-probe`, and `explore-lsp`.
5. Run the compiler tests after each batch and tighten schemas only when a real
   source asset needs the field.
