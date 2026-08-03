# Claude MCP permissions

Cheese-flow appends server-wide Claude Code permission rules for the MCP servers it installs: `mcp__hallouminate` after the Hallouminate plugin and `mcp__tilth` after Tilth registration. The append-unique edit preserves existing `~/.claude/settings.json` `permissions.allow` entries and each adapter verifies its own rule before reporting success.[^1]

[^1]: python/cheese_flow/adapters/hallouminate.py; python/cheese_flow/adapters/tilth.py; python/cheese_flow/install.py.