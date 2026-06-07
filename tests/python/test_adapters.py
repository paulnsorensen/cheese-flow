"""Verbatim port of the adapter-only vitest cases.

The TS test surface for adapters is the `adapter capabilities declarations`
describe block in `tests/capabilities.test.ts:10-102`. The remaining describe
blocks in that file (`fieldSupport`, `eventSupport`, `toolSupport`) drive
`src/lib/capabilities.ts` and land alongside the lib port in US-004.

The cursor-surface tests in `tests/cursor-surface.test.ts` exercise the
`emit_surface` callback, which depends on `parse_frontmatter`. Per the spec,
that callable + its tests land in US-004 alongside the frontmatter port.
"""

from __future__ import annotations

import pytest
from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.harness import PORTABLE_EVENTS, HarnessCapabilities


def test_every_adapter_has_a_capabilities_object() -> None:
    for name, adapter in HARNESS_ADAPTERS.items():
        assert isinstance(adapter.capabilities, HarnessCapabilities), f"{name} missing capabilities"
        assert isinstance(adapter.capabilities.skillFrontmatterKeys, frozenset)
        assert isinstance(adapter.capabilities.agentFrontmatterKeys, frozenset)
        assert isinstance(adapter.capabilities.hookEvents, frozenset)
        assert isinstance(adapter.capabilities.toolNames, frozenset)


def test_claude_code_declares_the_expected_claude_only_skill_keys() -> None:
    cc = HARNESS_ADAPTERS["claude-code"].capabilities
    assert "model" in cc.skillFrontmatterKeys
    assert "context" in cc.skillFrontmatterKeys


@pytest.mark.parametrize(
    "key",
    ["skills", "color", "effort", "disallowedTools", "permissionMode"],
)
def test_claude_code_declares_the_expected_claude_only_agent_keys(key: str) -> None:
    cc = HARNESS_ADAPTERS["claude-code"].capabilities
    assert key in cc.agentFrontmatterKeys, f"missing agent key: {key}"


def test_claude_code_declares_all_9_hook_events() -> None:
    cc = HARNESS_ADAPTERS["claude-code"].capabilities
    assert len(cc.hookEvents) == 9
    for event in (
        "sessionStart",
        "sessionEnd",
        "preToolUse",
        "postToolUse",
        "stop",
    ):
        assert event in cc.hookEvents, f"missing event: {event}"


@pytest.mark.parametrize(
    "tool",
    ["Agent", "Task", "NotebookEdit", "WebSearch", "WebFetch", "TodoWrite"],
)
def test_claude_code_declares_all_claude_only_tools(tool: str) -> None:
    cc = HARNESS_ADAPTERS["claude-code"].capabilities
    assert tool in cc.toolNames, f"missing tool: {tool}"


@pytest.mark.parametrize("name", ["codex", "copilot-cli"])
def test_codex_and_copilot_cli_declare_the_3_portable_hook_events(
    name: str,
) -> None:
    adapter = HARNESS_ADAPTERS[name]  # type: ignore[index]
    for event in PORTABLE_EVENTS:
        assert event in adapter.capabilities.hookEvents, f"{name} missing portable event: {event}"


def test_cursor_declares_zero_hook_events() -> None:
    assert len(HARNESS_ADAPTERS["cursor"].capabilities.hookEvents) == 0


@pytest.mark.parametrize("name", ["codex", "cursor", "copilot-cli"])
def test_non_claude_adapters_declare_no_claude_only_skill_or_agent_keys(
    name: str,
) -> None:
    cap = HARNESS_ADAPTERS[name].capabilities  # type: ignore[index]
    assert len(cap.skillFrontmatterKeys) == 0
    assert len(cap.agentFrontmatterKeys) == 0


@pytest.mark.parametrize("name", ["codex", "cursor", "copilot-cli"])
def test_non_claude_adapters_declare_no_tool_names(name: str) -> None:
    assert len(HARNESS_ADAPTERS[name].capabilities.toolNames) == 0  # type: ignore[index]


def test_registry_exposes_exactly_the_four_supported_harnesses() -> None:
    assert set(HARNESS_ADAPTERS.keys()) == {
        "claude-code",
        "codex",
        "cursor",
        "copilot-cli",
    }


def test_each_adapter_self_identifies_via_name_field() -> None:
    for harness, adapter in HARNESS_ADAPTERS.items():
        assert adapter.name == harness


def test_claude_code_and_codex_share_the_default_command_directory() -> None:
    assert HARNESS_ADAPTERS["claude-code"].commandDirectory == "commands"
    assert HARNESS_ADAPTERS["codex"].commandDirectory == "commands"


def test_cursor_and_copilot_cli_omit_the_command_directory() -> None:
    assert HARNESS_ADAPTERS["cursor"].commandDirectory is None
    assert HARNESS_ADAPTERS["copilot-cli"].commandDirectory is None


def test_only_cursor_skips_the_bootstrap_hook() -> None:
    for name, adapter in HARNESS_ADAPTERS.items():
        expected = name != "cursor"
        assert adapter.capabilities.bootstrapHook is expected


def test_cursor_returns_none_for_build_hook_config() -> None:
    cursor = HARNESS_ADAPTERS["cursor"]
    assert cursor.buildHookConfig({}) is None
