"""Verbatim port of the lib portion of `tests/capabilities.test.ts`.

The adapter capabilities declarations describe block lives in
``tests/python/test_adapters.py`` (US-003); this file ports the
``fieldSupport`` / ``eventSupport`` / ``toolSupport`` describe blocks that
exercise ``cheese_flow.lib.capabilities``.
"""

from __future__ import annotations

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.capabilities import event_support, field_support, tool_support
from cheese_flow.lib.harness import PORTABLE_EVENTS


def test_field_support_model_is_mapped_to_only_claude_code() -> None:
    assert field_support("skill").get("model") == ["claude-code"]


def test_field_support_context_is_mapped_to_only_claude_code() -> None:
    assert field_support("skill").get("context") == ["claude-code"]


def test_field_support_returns_a_map_for_agent_kind_with_all_expected_keys() -> None:
    support = field_support("agent")
    for key in ("skills", "color", "effort", "disallowedTools", "permissionMode"):
        assert key in support, f"missing agent key: {key}"


def test_field_support_portable_fields_are_absent_from_the_map() -> None:
    support = field_support("skill")
    assert "name" not in support
    assert "description" not in support


def test_event_support_portable_events_are_supported_by_all_hook_using_adapters() -> None:
    support = event_support()
    hook_adapters = sorted(
        name
        for name, adapter in HARNESS_ADAPTERS.items()
        if len(adapter.capabilities.hookEvents) > 0
    )
    for event in PORTABLE_EVENTS:
        supported_by = sorted(support.get(event, []))
        assert supported_by == hook_adapters


def test_event_support_stop_is_supported_only_by_claude_code() -> None:
    assert event_support().get("stop") == ["claude-code"]


def test_event_support_session_end_is_supported_only_by_claude_code() -> None:
    assert event_support().get("sessionEnd") == ["claude-code"]


def test_tool_support_all_tools_are_supported_only_by_claude_code() -> None:
    support = tool_support()
    for tool, supported_by in support.items():
        assert supported_by == ["claude-code"], f"{tool} should only be claude-code"


def test_tool_support_union_covers_full_claude_only_set() -> None:
    support = tool_support()
    for tool in ("Agent", "Task", "NotebookEdit", "WebSearch", "WebFetch", "TodoWrite"):
        assert tool in support, f"missing tool: {tool}"
