# Claude MCP permissions

Cheese-flow writes canonical server-wide wildcard rules to Claude Code's `permissions.allow`: `mcp__plugin_hallouminate_hallouminate__*` for Hallouminate's plugin-bundled MCP server and `mcp__tilth__*` for the directly registered Tilth server. Bare names such as `mcp__tilth` are invalid permission rules because Claude requires the `__<tool>` suffix, with `__*` selecting every tool on the server.[^1]

The edit targets `$CLAUDE_CONFIG_DIR/settings.json` when that nonblank override exists, otherwise `~/.claude/settings.json`. It preserves existing allow entries and follows a symlink to update its referent without replacing the link (`python/cheese_flow/adapters/native_config.py:36-61`, `python/cheese_flow/install.py:121-146`). Hallouminate supplies its plugin-qualified server name; Tilth uses its direct registration name (`python/cheese_flow/adapters/hallouminate.py:149-166`, `python/cheese_flow/adapters/tilth.py:172-186`).

A successful postcondition means the requested rule is configured, not that it wins every effective-policy layer. Claude deny, ask, enterprise-managed, and command-line policy can still take precedence.[^1]

[^1]: https://code.claude.com/docs/en/permissions