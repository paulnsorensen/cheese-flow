from __future__ import annotations

import pytest
from cheese_flow.profiles.errors import ProfilePermissionsError
from cheese_flow.profiles.rendering.permissions import (
    PermissionRuleError,
    bash_argv,
    named_mcp_tools,
    native_mcp_server_plugins,
    parse_mcp_rule,
    rewrite_native_mcp_rule,
    rewrite_native_mcp_rules,
    rewrite_skill_allowed_tools,
    validate_permission_rules,
    whole_server_mcp_allows,
)


def test_bash_argv_extracts_command_prefix_and_ignores_other_tools() -> None:
    assert bash_argv("Bash(git status:*)") == ["git", "status"]
    assert bash_argv("Read") is None


def test_parse_mcp_rule_preserves_server_and_tool_scope() -> None:
    assert parse_mcp_rule("mcp__tilth__read_file") == ("tilth", "read_file")
    assert parse_mcp_rule("mcp__tilth__*") == ("tilth", "*")
    assert parse_mcp_rule("Write") is None


def test_mcp_projection_keeps_named_and_whole_server_rules_separate() -> None:
    allow = ("mcp__tilth__*", "mcp__github__search")
    deny = ("mcp__tilth__delete", "mcp__github__admin")

    assert whole_server_mcp_allows(allow) == {"tilth"}
    assert named_mcp_tools(allow) == {"github": {"search"}}
    assert whole_server_mcp_allows(deny) == set()
    assert named_mcp_tools(deny) == {
        "tilth": {"delete"},
        "github": {"admin"},
    }


def test_validation_preserves_declared_order_and_duplicates() -> None:
    rules = ("Read", "mcp__tilth__read_file", "Read")

    assert validate_permission_rules(rules) == rules


def test_native_plugin_projection_rewrites_only_mapped_servers() -> None:
    plugins = (
        {
            "name": "tilth",
            "servers": ("tilth",),
            "claude_native": True,
        },
        {
            "name": "github",
            "servers": ("github",),
            "claude_native": False,
        },
    )
    server_plugins = native_mcp_server_plugins(plugins, "claude")

    assert server_plugins == {"tilth": "tilth"}
    assert rewrite_native_mcp_rule("mcp__tilth__read_file", server_plugins) == (
        "mcp__plugin_tilth_tilth__read_file"
    )
    assert rewrite_native_mcp_rules(
        ("mcp__tilth__read_file", "mcp__github__search", "Read"), server_plugins
    ) == [
        "mcp__plugin_tilth_tilth__read_file",
        "mcp__github__search",
        "Read",
    ]


def test_skill_allowed_tools_rewrites_inline_and_block_frontmatter() -> None:
    server_plugins = {"tilth": "tilth"}
    inline = "---\nallowed-tools: mcp__tilth__read_file, Read\n---\nBody\n"
    block = "---\nallowed-tools:\n  - mcp__tilth__read_file\n  - Read\n---\nBody\n"

    assert rewrite_skill_allowed_tools(server_plugins=server_plugins, text=inline) == (
        "---\nallowed-tools: mcp__plugin_tilth_tilth__read_file, Read\n---\nBody\n"
    )
    assert rewrite_skill_allowed_tools(server_plugins=server_plugins, text=block) == (
        "---\nallowed-tools:\n  - mcp__plugin_tilth_tilth__read_file\n  - Read\n---\nBody\n"
    )


@pytest.mark.parametrize(
    "rules",
    [
        ("",),
        ("Bash(git)",),
        ("Bash(:*)",),
        ("mcp__tilth",),
        ("mcp__tilth__",),
        ("mcp__tilth__read*",),
        ("Read", 42),
    ],
)
def test_malformed_permission_rules_raise_before_projection(
    rules: tuple[object, ...],
) -> None:
    with pytest.raises(ProfilePermissionsError, match="invalid permission rule"):
        validate_permission_rules(rules)

    with pytest.raises(PermissionRuleError, match="invalid permission rule"):
        named_mcp_tools(rules)  # type: ignore[arg-type]


def test_skill_malformed_allowed_tool_fails_before_rewrite() -> None:
    text = "---\nallowed-tools: mcp__tilth\n---\nBody\n"

    with pytest.raises(PermissionRuleError, match="invalid permission rule"):
        rewrite_skill_allowed_tools(text=text, server_plugins={})
