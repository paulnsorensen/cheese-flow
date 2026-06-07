"""Verbatim port of `tests/lint-skill-source.test.ts`.

Mirrors the vitest cases for ``lint_skill_source`` (re-exported from
``cheese_flow.lib.lint_skills``). Tests that depend on monkeypatching the
schemas module use ``monkeypatch`` / ``unittest.mock`` instead of vitest spies.
"""

from __future__ import annotations

from unittest.mock import patch

from cheese_flow.lib.lint_skills import lint_skill_source

VALID_BODY = "# Skill body\n\nUse this skill to do a thing.\n"


def test_accepts_a_valid_skill() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "valid-skill",
            "relativeFile": "valid-skill/SKILL.md",
            "source": (
                "---\nname: valid-skill\ndescription: Performs a clearly "
                "described action when the user asks for it.\n---\n" + VALID_BODY
            ),
        }
    )
    assert issues == []


def test_flags_name_directory_mismatch_as_an_error() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "real-name",
            "relativeFile": "real-name/SKILL.md",
            "source": (
                "---\nname: other-name\ndescription: Performs a clearly "
                "described action when the user asks for it.\n---\n" + VALID_BODY
            ),
        }
    )
    rules = [entry["rule"] for entry in issues]
    assert "name-matches-directory" in rules
    finding = next(entry for entry in issues if entry["rule"] == "name-matches-directory")
    assert finding["severity"] == "error"


def test_flags_invalid_kebab_case_names() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "BadName",
            "relativeFile": "BadName/SKILL.md",
            "source": (
                "---\nname: BadName\ndescription: Performs a clearly described "
                "action when the user asks for it.\n---\n" + VALID_BODY
            ),
        }
    )
    name_finding = next(
        (entry for entry in issues if entry["rule"] == "frontmatter:name"),
        None,
    )
    assert name_finding is not None
    assert name_finding["severity"] == "error"
    assert "name" in name_finding["message"]


def test_flags_missing_description() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "no-desc",
            "relativeFile": "no-desc/SKILL.md",
            "source": "---\nname: no-desc\n---\n" + VALID_BODY,
        }
    )
    desc_finding = next(
        (entry for entry in issues if entry["rule"].startswith("frontmatter:description")),
        None,
    )
    assert desc_finding is not None
    assert desc_finding["severity"] == "error"
    assert desc_finding["rule"] == "frontmatter:description"


def test_warns_when_the_description_is_too_short() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "short-desc",
            "relativeFile": "short-desc/SKILL.md",
            "source": ("---\nname: short-desc\ndescription: Too short.\n---\n" + VALID_BODY),
        }
    )
    warning = next(
        (entry for entry in issues if entry["rule"] == "description-too-short"),
        None,
    )
    assert warning is not None
    assert warning["severity"] == "warning"


def test_warns_when_the_body_exceeds_the_recommended_line_limit() -> None:
    long_body = "line\n" * 600
    issues = lint_skill_source(
        {
            "directoryName": "long-body",
            "relativeFile": "long-body/SKILL.md",
            "source": (
                "---\nname: long-body\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n" + long_body
            ),
        }
    )
    warning = next((entry for entry in issues if entry["rule"] == "body-too-long"), None)
    assert warning is not None
    assert warning["severity"] == "warning"


def test_flags_scalar_frontmatter_with_the_frontmatter_path_label() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "scalar",
            "relativeFile": "scalar/SKILL.md",
            "source": "---\n42\n---\n" + VALID_BODY,
        }
    )
    assert any(entry["rule"] == "frontmatter:<frontmatter>" for entry in issues)


def test_returns_a_parse_error_when_frontmatter_markers_are_missing() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "broken",
            "relativeFile": "broken/SKILL.md",
            "source": "no frontmatter here\n",
        }
    )
    assert len(issues) == 1
    assert issues[0]["rule"] == "frontmatter-parse"
    assert issues[0]["severity"] == "error"


def test_flags_compatibility_strings_exceeding_500_characters() -> None:
    long_compat = "x" * 600
    issues = lint_skill_source(
        {
            "directoryName": "wide-compat",
            "relativeFile": "wide-compat/SKILL.md",
            "source": (
                "---\nname: wide-compat\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                f"compatibility: {long_compat}\n---\n" + VALID_BODY
            ),
        }
    )
    compat_finding = next(
        (entry for entry in issues if entry["rule"].startswith("frontmatter:compatibility")),
        None,
    )
    assert compat_finding is not None
    assert compat_finding["severity"] == "error"
    assert compat_finding["rule"] == "frontmatter:compatibility"


def test_warns_when_allowed_tools_uses_claude_code_permission_glob_syntax() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "claude-perms",
            "relativeFile": "claude-perms/SKILL.md",
            "source": (
                "---\nname: claude-perms\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "allowed-tools: Bash(git diff:*), Read\n---\n" + VALID_BODY
            ),
        }
    )
    finding = next(
        (entry for entry in issues if entry["rule"] == "allowed-tools-claude-permission-syntax"),
        None,
    )
    assert finding is not None
    assert finding["severity"] == "warning"
    assert "Bash(git diff:*)" in finding["message"]


def test_warns_when_allowed_tools_is_an_array_using_claude_permission_glob() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "claude-perms-array",
            "relativeFile": "claude-perms-array/SKILL.md",
            "source": (
                "---\nname: claude-perms-array\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "allowed-tools:\n  - Bash(gh:*)\n  - Read\n---\n" + VALID_BODY
            ),
        }
    )
    finding = next(
        (entry for entry in issues if entry["rule"] == "allowed-tools-claude-permission-syntax"),
        None,
    )
    assert finding is not None
    assert finding["severity"] == "warning"
    assert "Bash(gh:*)" in finding["message"]


def test_does_not_warn_on_bare_tool_names_in_allowed_tools() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "bare-tools",
            "relativeFile": "bare-tools/SKILL.md",
            "source": (
                "---\nname: bare-tools\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "allowed-tools:\n  - read\n  - write\n  - bash\n---\n" + VALID_BODY
            ),
        }
    )
    assert not any(
        entry["rule"].startswith("allowed-tools-claude-permission-syntax") for entry in issues
    )


def test_warns_when_body_references_claude_only_agent_tool() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "agent-call",
            "relativeFile": "agent-call/SKILL.md",
            "source": (
                "---\nname: agent-call\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                'Use Agent(subagent_type="foo") to spawn a sub-agent.\n'
            ),
        }
    )
    finding = next(
        (entry for entry in issues if entry["rule"] == "body-claude-only-tool"),
        None,
    )
    assert finding is not None
    assert finding["severity"] == "warning"
    assert "Agent" in finding["message"]


def test_warns_when_body_references_claude_only_task_tool() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "task-call",
            "relativeFile": "task-call/SKILL.md",
            "source": (
                "---\nname: task-call\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                "Dispatch via Task(...)\n"
            ),
        }
    )
    finding = next(
        (entry for entry in issues if entry["rule"] == "body-claude-only-tool"),
        None,
    )
    assert finding is not None
    assert finding["severity"] == "warning"
    assert "Task" in finding["message"]


def test_warns_when_body_references_pascal_case_hook_event_names() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "pascal-hook",
            "relativeFile": "pascal-hook/SKILL.md",
            "source": (
                "---\nname: pascal-hook\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                "Fires on SessionStart and PreToolUse events.\n"
            ),
        }
    )
    findings = [entry for entry in issues if entry["rule"] == "body-pascal-hook-event"]
    assert len(findings) == 2
    assert all(f["severity"] == "warning" for f in findings)


def test_does_not_flag_camel_case_hook_event_names_in_body() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "camel-hook",
            "relativeFile": "camel-hook/SKILL.md",
            "source": (
                "---\nname: camel-hook\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                "Fires on sessionStart and preToolUse events.\n"
            ),
        }
    )
    assert not any(entry["rule"] == "body-pascal-hook-event" for entry in issues)


def test_stringifies_non_error_throws_from_parse_skill_frontmatter() -> None:
    def _raise(_: object):
        raise RuntimeError("stringy doom")

    with patch(
        "cheese_flow.lib.lint_skill_rules.parse_skill_frontmatter",
        side_effect=_raise,
    ):
        issues = lint_skill_source(
            {
                "directoryName": "stringy",
                "relativeFile": "stringy/SKILL.md",
                "source": (
                    "---\nname: stringy\ndescription: A perfectly fine "
                    "description that is long enough for discovery.\n---\n" + VALID_BODY
                ),
            }
        )
    finding = next(
        (entry for entry in issues if entry["rule"] == "frontmatter-parse"),
        None,
    )
    assert finding is not None
    assert finding["message"] == "stringy doom"


def test_ignores_allowed_tools_when_it_is_neither_string_nor_array() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "weird-tools",
            "relativeFile": "weird-tools/SKILL.md",
            "source": (
                "---\nname: weird-tools\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "allowed-tools: 42\n---\n" + VALID_BODY
            ),
        }
    )
    assert not any(entry["rule"] == "allowed-tools-claude-permission-syntax" for entry in issues)


def test_converts_a_non_zod_error_throw_from_parse_skill_frontmatter() -> None:
    def _raise(_: object):
        raise Exception("synthetic non-zod failure")

    with patch(
        "cheese_flow.lib.lint_skill_rules.parse_skill_frontmatter",
        side_effect=_raise,
    ):
        issues = lint_skill_source(
            {
                "directoryName": "weird-throw",
                "relativeFile": "weird-throw/SKILL.md",
                "source": (
                    "---\nname: weird-throw\ndescription: A perfectly fine "
                    "description that is long enough for discovery.\n---\n" + VALID_BODY
                ),
            }
        )
    finding = next(
        (entry for entry in issues if entry["rule"] == "frontmatter-parse"),
        None,
    )
    assert finding is not None
    assert "synthetic non-zod failure" in finding["message"]


def test_flags_claude_only_frontmatter_fields_via_adapter_capabilities() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "claude-only-fields",
            "relativeFile": "claude-only-fields/SKILL.md",
            "source": (
                "---\nname: claude-only-fields\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "model: opus\ncontext: fork\n---\n" + VALID_BODY
            ),
        }
    )
    portability = [entry for entry in issues if entry["rule"] == "frontmatter-portability"]
    assert len(portability) == 2
    assert all(entry["severity"] == "warning" for entry in portability)


def test_does_not_flag_context_inline_because_it_is_the_portable_default() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "inline-context",
            "relativeFile": "inline-context/SKILL.md",
            "source": (
                "---\nname: inline-context\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "context: inline\n---\n" + VALID_BODY
            ),
        }
    )
    assert not any(entry["rule"] == "frontmatter-portability" for entry in issues)


def test_context_fork_produces_exactly_one_portability_warning() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "fork-context",
            "relativeFile": "fork-context/SKILL.md",
            "source": (
                "---\nname: fork-context\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "context: fork\n---\n" + VALID_BODY
            ),
        }
    )
    portability = [entry for entry in issues if entry["rule"] == "frontmatter-portability"]
    assert len(portability) == 1


def test_stop_in_body_emits_body_harness_only_hook_event_not_pascal() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "stop-hook",
            "relativeFile": "stop-hook/SKILL.md",
            "source": (
                "---\nname: stop-hook\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                "Fires on Stop events.\n"
            ),
        }
    )
    stop_finding = next(
        (entry for entry in issues if entry["rule"] == "body-harness-only-hook-event"),
        None,
    )
    assert stop_finding is not None
    assert stop_finding["severity"] == "warning"
    assert "Stop" in stop_finding["message"]
    assert not any(entry["rule"] == "body-pascal-hook-event" for entry in issues)


def test_stop_camel_case_in_body_does_not_emit_any_hook_warning() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "stop-camel",
            "relativeFile": "stop-camel/SKILL.md",
            "source": (
                "---\nname: stop-camel\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n# Body\n"
                "Fires on stop events.\n"
            ),
        }
    )
    assert not any(
        entry["rule"] in ("body-harness-only-hook-event", "body-pascal-hook-event")
        for entry in issues
    )


def test_runs_portability_checks_even_when_frontmatter_validation_fails() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "BadName",
            "relativeFile": "BadName/SKILL.md",
            "source": (
                "---\nname: BadName\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n"
                "context: fork\n---\n# Body\nUse Agent(...) for sub-agent dispatch.\n"
            ),
        }
    )
    name_finding = next((entry for entry in issues if entry["rule"] == "frontmatter:name"), None)
    assert name_finding is not None
    assert name_finding["severity"] == "error"

    portability_finding = next(
        (entry for entry in issues if entry["rule"] == "frontmatter-portability"),
        None,
    )
    assert portability_finding is not None
    assert portability_finding["severity"] == "warning"

    body_finding = next(
        (entry for entry in issues if entry["rule"] == "body-claude-only-tool"),
        None,
    )
    assert body_finding is not None
    assert body_finding["severity"] == "warning"
    assert "Agent" in body_finding["message"]


def test_attaches_an_absolute_skill_md_line_number_to_body_findings() -> None:
    issues = lint_skill_source(
        {
            "directoryName": "agent-line",
            "relativeFile": "agent-line/SKILL.md",
            "source": (
                "---\nname: agent-line\ndescription: A perfectly fine "
                "description that is long enough for discovery.\n---\n"
                "first body line\nsecond line uses Agent(...)\n"
            ),
        }
    )
    finding = next(
        (entry for entry in issues if entry["rule"] == "body-claude-only-tool"),
        None,
    )
    assert finding is not None
    # Frontmatter spans SKILL.md lines 1-4 (`---`, name, description, `---`).
    # Body line 2 is the Agent(...) line, so absolute = 4 + 2 = 6.
    assert finding.get("line") == 6
