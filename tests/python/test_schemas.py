"""Verbatim port of the schemas-related vitest cases from `tests/compiler.test.ts`.

Source cases live in the `frontmatter and schema helpers` describe block
(`tests/compiler.test.ts:917-959`). The `parseFrontmatter`-only assertions
land with US-004 alongside the frontmatter port; this file ports the
schema-helper assertions that exercise `src/lib/schemas.ts` directly.
"""

from __future__ import annotations

import pytest
from cheese_flow.lib.schemas import (
    HarnessModel,
    SkillFrontmatter,
    parse_agent_frontmatter,
    parse_command_frontmatter,
    parse_skill_frontmatter,
    resolve_model,
)
from pydantic import ValidationError


def test_resolve_model_falls_back_to_default_when_harness_key_missing() -> None:
    models = HarnessModel(default="gpt-5.1-codex")
    assert resolve_model(models, "claude-code") == "gpt-5.1-codex"


def test_resolve_model_returns_harness_specific_value_when_present() -> None:
    models = HarnessModel.model_validate(
        {"default": "gpt-5.1-codex", "claude-code": "claude-opus-4-7"},
    )
    assert resolve_model(models, "claude-code") == "claude-opus-4-7"


def test_skill_frontmatter_accepts_string_form_of_allowed_tools() -> None:
    skill = parse_skill_frontmatter(
        {
            "name": "basic-skill",
            "description": "Portable skill",
            "allowed-tools": "read write",
        },
    )
    assert skill.allowed_tools == "read write"


def test_skill_frontmatter_accepts_array_form_of_allowed_tools() -> None:
    skill = parse_skill_frontmatter(
        {
            "name": "basic-skill",
            "description": "Portable skill",
            "allowed-tools": ["read", "write"],
        },
    )
    assert skill.allowed_tools == ["read", "write"]


def test_agent_frontmatter_defaults_tool_lists_to_empty() -> None:
    agent = parse_agent_frontmatter(
        {
            "name": "basic-agent",
            "description": "Portable agent",
            "models": {"default": "gpt-5.1-codex"},
        },
    )
    assert agent.tools == []
    assert agent.skills == []
    assert agent.disallowedTools == []


def test_skill_frontmatter_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_skill_frontmatter(
            {
                "name": "basic-skill",
                "description": "Portable skill",
                "extra": "nope",
            },
        )


def test_agent_frontmatter_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_agent_frontmatter(
            {
                "name": "basic-agent",
                "description": "Portable agent",
                "models": {"default": "gpt-5.1-codex"},
                "extra": "nope",
            },
        )


def test_command_frontmatter_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_command_frontmatter(
            {
                "name": "basic-command",
                "description": "Portable command",
                "extra": "nope",
            },
        )


def test_slug_rejects_uppercase_names() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter.model_validate(
            {"name": "BadSlug", "description": "x"},
        )


def test_slug_rejects_underscores() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter.model_validate(
            {"name": "bad_slug", "description": "x"},
        )


def test_slug_accepts_kebab_case() -> None:
    skill = SkillFrontmatter.model_validate(
        {"name": "kebab-case-name", "description": "x"},
    )
    assert skill.name == "kebab-case-name"


def test_description_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter.model_validate(
            {"name": "ok", "description": "x" * 1025},
        )


def test_agent_frontmatter_validates_effort_enum() -> None:
    with pytest.raises(ValidationError):
        parse_agent_frontmatter(
            {
                "name": "basic-agent",
                "description": "Portable agent",
                "models": {"default": "gpt-5.1-codex"},
                "effort": "ultra",
            },
        )


def test_agent_frontmatter_validates_permission_mode_enum() -> None:
    with pytest.raises(ValidationError):
        parse_agent_frontmatter(
            {
                "name": "basic-agent",
                "description": "Portable agent",
                "models": {"default": "gpt-5.1-codex"},
                "permissionMode": "rogue",
            },
        )


def test_skill_frontmatter_validates_context_enum() -> None:
    with pytest.raises(ValidationError):
        parse_skill_frontmatter(
            {
                "name": "basic-skill",
                "description": "Portable skill",
                "context": "remote",
            },
        )


def test_harness_model_accepts_per_harness_overrides() -> None:
    models = HarnessModel.model_validate(
        {
            "default": "gpt-5.1-codex",
            "claude-code": "claude-opus-4-7",
            "codex": "gpt-5.1-codex",
            "cursor": "auto",
            "copilot-cli": "gpt-5",
        },
    )
    assert resolve_model(models, "claude-code") == "claude-opus-4-7"
    assert resolve_model(models, "codex") == "gpt-5.1-codex"
    assert resolve_model(models, "cursor") == "auto"
    assert resolve_model(models, "copilot-cli") == "gpt-5"


def test_harness_model_requires_default() -> None:
    with pytest.raises(ValidationError):
        HarnessModel.model_validate({"claude-code": "claude-opus-4-7"})


def test_agent_skills_require_kebab_slug() -> None:
    with pytest.raises(ValidationError):
        parse_agent_frontmatter(
            {
                "name": "basic-agent",
                "description": "Portable agent",
                "models": {"default": "gpt-5.1-codex"},
                "skills": ["BadSlug"],
            },
        )


def test_command_frontmatter_accepts_argument_hint_alias() -> None:
    cmd = parse_command_frontmatter(
        {
            "name": "basic-command",
            "description": "Portable command",
            "argument-hint": "<path>",
        },
    )
    assert cmd.argument_hint == "<path>"
