"""Verbatim port of `tests/harness-compat.test.ts`.

The TS suite exercises four entry points: ``checkAllowedToolsPortability``,
``checkFrontmatterPortability``, ``checkBodyHarnessIdioms``, and
``compileTestSkill``. The registry-mutation case in TS rebinds
``adapter.capabilities`` directly; in Python the dataclass is frozen, so the
port replaces the registry entry with a new ``HarnessAdapter`` and restores
the original on teardown.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.capabilities import field_support
from cheese_flow.lib.harness import HarnessAdapter, HarnessCapabilities
from cheese_flow.lib.harness_compat import (
    check_allowed_tools_portability,
    check_body_harness_idioms,
    check_frontmatter_portability,
    compile_test_skill,
)

# --- check_allowed_tools_portability -------------------------------------------------


def test_returns_no_findings_when_allowed_tools_is_undefined() -> None:
    assert check_allowed_tools_portability(None) == []


def test_returns_no_findings_on_bare_tool_names_string_form() -> None:
    assert check_allowed_tools_portability("read write bash") == []


def test_returns_no_findings_on_bare_tool_names_array_form() -> None:
    assert check_allowed_tools_portability(["read", "write", "bash"]) == []


def test_flags_claude_permission_glob_in_string_form() -> None:
    findings = check_allowed_tools_portability("Bash(git diff:*), Read")
    assert len(findings) == 1
    assert findings[0]["rule"] == "allowed-tools-claude-permission-syntax"
    assert findings[0]["severity"] == "warning"


def test_flags_claude_permission_glob_in_array_form() -> None:
    findings = check_allowed_tools_portability(
        ["Bash(gh:*)", "mcp__tilth__tilth_search"],
    )
    assert len(findings) == 1
    assert findings[0]["rule"] == "allowed-tools-claude-permission-syntax"
    assert findings[0]["severity"] == "warning"
    assert "Bash(gh:*)" in findings[0]["message"]


def test_flags_all_occurrences_when_multiple_permission_globs_are_present() -> None:
    findings = check_allowed_tools_portability("Bash(git:*), Bash(gh:*)")
    assert len(findings) == 2
    assert "Bash(git:*)" in findings[0]["message"]
    assert "Bash(gh:*)" in findings[1]["message"]


def test_flags_lowercase_permission_glob_syntax() -> None:
    findings = check_allowed_tools_portability("bash(git diff:*)")
    assert len(findings) == 1
    assert findings[0]["rule"] == "allowed-tools-claude-permission-syntax"
    assert findings[0]["severity"] == "warning"
    assert "bash(git diff:*)" in findings[0]["message"]


# --- check_frontmatter_portability ---------------------------------------------------


def test_returns_no_findings_for_skills_using_only_portable_fields() -> None:
    assert (
        check_frontmatter_portability({"name": "x", "description": "y"}, "skill") == []
    )


def test_flags_model_and_context_fork_on_a_skill_2_findings() -> None:
    findings = check_frontmatter_portability(
        {"name": "x", "description": "y", "model": "opus", "context": "fork"},
        "skill",
    )
    assert len(findings) == 2
    assert all(f["rule"] == "frontmatter-portability" for f in findings)
    assert any('"model"' in f["message"] for f in findings)
    assert any('"context"' in f["message"] for f in findings)


def test_does_not_flag_context_inline_because_it_is_the_portable_default() -> None:
    findings = check_frontmatter_portability(
        {"name": "x", "description": "y", "context": "inline"},
        "skill",
    )
    assert findings == []


def test_flags_all_claude_only_agent_fields() -> None:
    findings = check_frontmatter_portability(
        {
            "name": "x",
            "description": "y",
            "skills": ["foo"],
            "color": "red",
            "effort": "high",
            "disallowedTools": ["Edit"],
            "permissionMode": "default",
        },
        "agent",
    )
    assert len(findings) == 5
    assert all(f["rule"] == "frontmatter-portability" for f in findings)


def test_is_driven_by_adapter_capabilities_not_hardcoded_constants() -> None:
    # model is supported only by claude-code; if a future adapter also declares it,
    # the map grows and the warning would no longer fire for that adapter.
    # Verify the current mapping is capability-driven.
    support = field_support("skill")
    assert support["model"] == ["claude-code"]
    assert support["context"] == ["claude-code"]


def test_warning_suppresses_when_every_adapter_declares_the_field() -> None:
    # Plan §6 regression: prove the lint is data-driven by mutating the registry
    # so every adapter declares `model` in skillFrontmatterKeys. The warning
    # must stop firing — adding a portable field means editing capabilities,
    # not the lint.
    skills_before = check_frontmatter_portability(
        {"name": "x", "description": "y", "model": "opus"},
        "skill",
    )
    assert len(skills_before) == 1

    original_adapters: dict[str, HarnessAdapter] = dict(HARNESS_ADAPTERS)
    try:
        for name, adapter in original_adapters.items():
            HARNESS_ADAPTERS[name] = replace(  # type: ignore[index]
                adapter,
                capabilities=replace(
                    adapter.capabilities,
                    skillFrontmatterKeys=frozenset(
                        {*adapter.capabilities.skillFrontmatterKeys, "model"},
                    ),
                ),
            )
        fifth_template = original_adapters["claude-code"]
        fifth = replace(
            fifth_template,
            displayName="Fifth",
            outputRoot=".fifth",
            capabilities=HarnessCapabilities(
                skillFrontmatterKeys=frozenset({"model"}),
                agentFrontmatterKeys=frozenset(),
                hookEvents=frozenset(),
                toolNames=frozenset(),
                bootstrapHook=False,
            ),
        )
        HARNESS_ADAPTERS["fifth"] = fifth  # type: ignore[index]

        skills_after = check_frontmatter_portability(
            {"name": "x", "description": "y", "model": "opus"},
            "skill",
        )
        assert skills_after == []
    finally:
        if "fifth" in HARNESS_ADAPTERS:
            del HARNESS_ADAPTERS["fifth"]  # type: ignore[arg-type]
        for name, adapter in original_adapters.items():
            HARNESS_ADAPTERS[name] = adapter  # type: ignore[index]


# --- check_body_harness_idioms -------------------------------------------------------


def test_returns_no_findings_on_plain_markdown_body() -> None:
    body = "# Heading\n\nUse the harness's native tools.\n"
    assert check_body_harness_idioms(body) == []


def test_flags_agent_call_sites() -> None:
    findings = check_body_harness_idioms('Use Agent(subagent_type="x")')
    assert len(findings) == 1
    assert findings[0]["rule"] == "body-claude-only-tool"


def test_flags_task_call_sites() -> None:
    findings = check_body_harness_idioms("Spawn via Task(...).")
    assert len(findings) == 1
    assert "Task" in findings[0]["message"]


def test_flags_portable_pascalcase_hook_events_with_body_pascal_hook_event() -> None:
    findings = check_body_harness_idioms(
        "Fires SessionStart, PreToolUse, PostToolUse.",
    )
    matching = [f for f in findings if f["rule"] == "body-pascal-hook-event"]
    assert len(matching) == 3


def test_flags_claude_only_pascalcase_hook_events_with_body_harness_only_hook_event() -> None:
    findings = check_body_harness_idioms(
        "Fires Stop, SubagentStop, Notification.",
    )
    matching = [f for f in findings if f["rule"] == "body-harness-only-hook-event"]
    assert len(matching) == 3
    assert all(f["severity"] == "warning" for f in findings)


def test_stop_emits_body_harness_only_hook_event_not_body_pascal_hook_event() -> None:
    findings = check_body_harness_idioms("Triggers on Stop.")
    stop_finding = next((f for f in findings if "Stop" in f["message"]), None)
    assert stop_finding is not None
    assert stop_finding["rule"] == "body-harness-only-hook-event"


def test_does_not_flag_camelcase_hook_events() -> None:
    findings = check_body_harness_idioms(
        "Fires sessionStart, preToolUse, postToolUse.",
    )
    assert findings == []


def test_does_not_flag_camelcase_stop_in_body() -> None:
    findings = check_body_harness_idioms("Fires stop, subagentStop events.")
    assert not any(
        f["rule"] in {"body-pascal-hook-event", "body-harness-only-hook-event"}
        for f in findings
    )


def test_flags_claude_only_tools_beyond_agent_task() -> None:
    findings = check_body_harness_idioms(
        "Use NotebookEdit(...) and WebSearch(...) and TodoWrite(...) and WebFetch(...).",
    )
    tools = [f["message"] for f in findings if f["rule"] == "body-claude-only-tool"]
    assert any("NotebookEdit" in m for m in tools)
    assert any("WebSearch" in m for m in tools)
    assert any("TodoWrite" in m for m in tools)
    assert any("WebFetch" in m for m in tools)


def test_flags_harness_specific_path_markers() -> None:
    findings = check_body_harness_idioms(
        "See .claude/specs and .codex/agents and .cursor/rules and AGENTS.md.",
    )
    markers = [f["message"] for f in findings if f["rule"] == "body-harness-path-marker"]
    assert any(".claude/" in m for m in markers)
    assert any(".codex/" in m for m in markers)
    assert any(".cursor/" in m for m in markers)
    assert any("AGENTS.md" in m for m in markers)


def test_attaches_a_1_based_line_number_to_each_body_finding() -> None:
    body = "line 1\nline 2 with Agent(\nline 3\n"
    findings = check_body_harness_idioms(body)
    agent_finding = next(
        (f for f in findings if f["rule"] == "body-claude-only-tool"), None
    )
    assert agent_finding is not None
    assert agent_finding.get("line") == 2


# --- compile_test_skill --------------------------------------------------------------


_VALID_SKILL = (
    "---\nname: my-skill\ndescription: A long-enough description for portable "
    "discovery.\n---\n# Body\nDo something useful.\n"
)


def test_returns_no_findings_for_a_valid_skill() -> None:
    findings = asyncio.run(compile_test_skill("my-skill", _VALID_SKILL))
    assert findings == []


def test_reports_a_compile_failure_for_every_adapter_when_frontmatter_is_malformed() -> None:
    malformed = "no frontmatter at all\n"
    findings = asyncio.run(compile_test_skill("broken-skill", malformed))
    assert len(findings) == 4
    assert all(f["severity"] == "error" for f in findings)
    rules = [f["rule"] for f in findings]
    for harness in ("claude-code", "codex", "cursor", "copilot-cli"):
        assert f"compile-{harness}-failed" in rules


def test_surfaces_the_directory_name_mismatch_as_an_adapter_level_compile_error() -> None:
    mismatched = (
        "---\nname: not-the-folder\ndescription: A long-enough description for "
        "portable discovery.\n---\n# Body\nSomething useful.\n"
    )
    findings = asyncio.run(compile_test_skill("expected-folder", mismatched))
    assert any("must match frontmatter name" in f["message"] for f in findings)
