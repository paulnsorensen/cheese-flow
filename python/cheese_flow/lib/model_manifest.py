"""Port of `src/lib/model-manifest.ts` — read + apply harness model overrides."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from cheese_flow.lib.harness import HarnessName

MODEL_MANIFEST_FILE = "models.yaml"

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
AgentSlugStr = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]


class HarnessPins(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    claude_code: dict[NonEmptyStr, NonEmptyStr] | None = Field(
        default=None, alias="claude-code"
    )
    codex: dict[NonEmptyStr, NonEmptyStr] | None = None
    cursor: dict[NonEmptyStr, NonEmptyStr] | None = None
    copilot_cli: dict[NonEmptyStr, NonEmptyStr] | None = Field(
        default=None, alias="copilot-cli"
    )

    def get(self, harness: HarnessName) -> dict[str, str] | None:
        if harness == "claude-code":
            return self.claude_code
        if harness == "codex":
            return self.codex
        if harness == "cursor":
            return self.cursor
        return self.copilot_cli


class HarnessOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    claude_code: NonEmptyStr | None = Field(default=None, alias="claude-code")
    codex: NonEmptyStr | None = None
    cursor: NonEmptyStr | None = None
    copilot_cli: NonEmptyStr | None = Field(default=None, alias="copilot-cli")

    def get(self, harness: HarnessName) -> str | None:
        if harness == "claude-code":
            return self.claude_code
        if harness == "codex":
            return self.codex
        if harness == "cursor":
            return self.cursor
        return self.copilot_cli


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pins: HarnessPins | None = None
    overrides: dict[AgentSlugStr, HarnessOverride] | None = None


_YAML = YAML(typ="safe")


def _read_yaml(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    return _YAML.load(StringIO(raw))


def read_model_manifest(project_root: str | Path) -> ModelManifest | None:
    """Return the parsed manifest or ``None`` when ``models.yaml`` is absent."""
    manifest_path = Path(project_root) / MODEL_MANIFEST_FILE
    if not manifest_path.exists():
        return None

    try:
        parsed = _read_yaml(manifest_path)
    except YAMLError as error:
        raise ValueError(
            f"Invalid models.yaml at {manifest_path}: {error}"
        ) from error

    payload = parsed if parsed is not None else {}

    try:
        return ModelManifest.model_validate(payload)
    except ValidationError as error:
        raise ValueError(
            f"Invalid models.yaml at {manifest_path}: {error}"
        ) from error


def apply_model_manifest(
    *,
    model: str,
    agent_name: str,
    harness: HarnessName,
    manifest: ModelManifest | None,
) -> str:
    """Resolve ``model`` against the optional manifest, mirroring the TS rules."""
    if manifest is None:
        return model
    overrides = manifest.overrides or {}
    override_entry = overrides.get(agent_name)
    if override_entry is not None:
        override_value = override_entry.get(harness)
        if override_value is not None:
            return override_value
    pins = manifest.pins
    if pins is not None:
        harness_pins = pins.get(harness)
        if harness_pins is not None:
            pin = harness_pins.get(model)
            if pin is not None:
                return pin
    return model
