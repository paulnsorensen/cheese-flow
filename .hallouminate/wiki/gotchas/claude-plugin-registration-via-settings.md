# Claude plugin registration goes through settings.json, never the `claude` CLI

Hallouminate's Claude Code registration is declared as two `ConfigEdit`s against
`settings.json` (`extraKnownMarketplaces.hallouminate` and
`enabledPlugins.hallouminate@hallouminate`), not shelled out to `claude plugin
marketplace add` / `claude plugin install` the way Codex's registration is.[^1]

## Why: the headless target has no `claude` on PATH and a locked-down proxy

The installer must converge on a Claude Cloud setup script, which runs with no
`claude` executable on PATH and sits behind a GitHub proxy that refuses to clone
any repository not already attached to the session. A CLI-driven install cannot
complete there. Declaring the marketplace and plugin entries directly in
`settings.json` instead defers the actual catalog fetch to Claude Code's own
session start, which the cloud environment permits — and the same declarative
edit converges identically on a developer machine, so there is no
environment-specific branch in the adapter.

This is why `PLUGIN_CLIS` in `python/cheese_flow/adapters/hallouminate.py`
deliberately omits `"claude-code"`: Codex still goes through its native CLI
(`codex plugin add`), but Claude Code is handled entirely by
`_claude_registration_steps`, which writes both edits under `Phase.REGISTER`
with the plugin edit depending on the marketplace edit.

## Postcondition follows the edit, not a CLI query

Because there is no CLI call to inspect, the postcondition for both steps is
`config_edit_holds(step.config_edit)` — it reads `settings.json` back and
checks the declared pointer/value, the same primitive `claude-mcp-permissions`
describes for MCP permission rules. `_check_marketplace` / `_check_plugin`
(the `claude plugin ... --json` parsing path) only run for harnesses that still
register through a CLI.

## Related

- [Claude MCP permissions](./claude-mcp-permissions.md) — same `settings.json` edit/read machinery, applied to permission rules instead of plugin registration.
- [V1 installer boundary](../architecture/v1-installer-boundary.md) — Hallouminate setup delegates to its own binary/plugin/config surface; this page is the concrete mechanism for the Claude Code leg of that delegation.

[^1]: `python/cheese_flow/adapters/hallouminate.py:26-40` (constants and `PLUGIN_CLIS` comment), `:129-131` (dispatch), `:315-352` (`_claude_registration_steps`), `:278-283` (`_check_marketplace`/`_check_plugin` CLI-only fallback). Introduced by commit `8b56923` ("fix(hallouminate): declare Claude Code plugin registration in settings, not via the claude CLI (#101)").
