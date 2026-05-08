"""Pydantic v2 ports of the zod schemas in `src/lib/schemas.ts`.

`extra="forbid"` mirrors zod's `.strict()` (where present); harnessModelSchema
in TS has no `.strict()`, so its Python counterpart leaves `extra` at the
pydantic default (ignore).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EffortLevel = Literal["low", "medium", "high"]
PermissionMode = Literal["plan", "acceptEdits", "default"]
SkillContext = Literal["fork", "inline"]
HarnessName = Literal["claude-code", "codex", "cursor", "copilot-cli"]

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

Slug = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=SLUG_PATTERN),
]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
DescriptionStr = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
CompatibilityStr = Annotated[str, StringConstraints(min_length=1, max_length=500)]
ArgumentHintStr = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class HarnessModel(BaseModel):
    """Mirror of `harnessModelSchema` (no `.strict()` — extras stripped)."""

    model_config = ConfigDict(populate_by_name=True)

    default: NonEmptyStr
    claude_code: NonEmptyStr | None = Field(default=None, alias="claude-code")
    codex: NonEmptyStr | None = None
    cursor: NonEmptyStr | None = None
    copilot_cli: NonEmptyStr | None = Field(default=None, alias="copilot-cli")

    def get(self, harness: HarnessName) -> str | None:
        """Return the configured model for `harness`, or None if unset."""
        if harness == "claude-code":
            return self.claude_code
        if harness == "codex":
            return self.codex
        if harness == "cursor":
            return self.cursor
        return self.copilot_cli


class SkillFrontmatter(BaseModel):
    """Mirror of `skillFrontmatterSchema` (`.strict()`)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    license: NonEmptyStr | None = None
    compatibility: CompatibilityStr | None = None
    allowed_tools: list[NonEmptyStr] | NonEmptyStr | None = Field(
        default=None, alias="allowed-tools"
    )
    metadata: dict[str, Any] | None = None
    name: Slug
    description: DescriptionStr
    model: NonEmptyStr | None = None
    context: SkillContext | None = None


class CommandFrontmatter(BaseModel):
    """Mirror of `commandFrontmatterSchema` (`.strict()`)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: Slug
    description: DescriptionStr
    argument_hint: ArgumentHintStr | None = Field(default=None, alias="argument-hint")


class AgentFrontmatter(BaseModel):
    """Mirror of `agentFrontmatterSchema` (`.strict()`)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: Slug
    description: DescriptionStr
    models: HarnessModel
    tools: list[NonEmptyStr] = Field(default_factory=list)
    skills: list[Slug] = Field(default_factory=list)
    color: NonEmptyStr | None = None
    effort: EffortLevel | None = None
    disallowedTools: list[NonEmptyStr] = Field(default_factory=list)
    permissionMode: PermissionMode | None = None
    metadata: dict[str, Any] | None = None


class PluginAuthorModel(BaseModel):
    """Mirror of `pluginMetadataSchema.author` (zod)."""

    model_config = ConfigDict(populate_by_name=True)

    name: NonEmptyStr
    email: str | None = None
    url: str | None = None


class PluginMetadataModel(BaseModel):
    """Mirror of `pluginMetadataSchema` from `src/domain/harness.ts`."""

    model_config = ConfigDict(populate_by_name=True)

    name: NonEmptyStr
    version: NonEmptyStr
    description: NonEmptyStr
    author: PluginAuthorModel
    license: NonEmptyStr
    repository: NonEmptyStr
    homepage: str | None = None
    keywords: list[str] | None = None


def parse_plugin_metadata(data: Any) -> PluginMetadataModel:
    return PluginMetadataModel.model_validate(data)


def parse_skill_frontmatter(data: Any) -> SkillFrontmatter:
    return SkillFrontmatter.model_validate(data)


def parse_command_frontmatter(data: Any) -> CommandFrontmatter:
    return CommandFrontmatter.model_validate(data)


def parse_agent_frontmatter(data: Any) -> AgentFrontmatter:
    return AgentFrontmatter.model_validate(data)


def resolve_model(models: HarnessModel, harness: HarnessName) -> str:
    """Return the model for `harness`, falling back to `models.default`."""
    return models.get(harness) or models.default
