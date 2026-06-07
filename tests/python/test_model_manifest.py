"""Verbatim port of `tests/model-manifest.test.ts`."""

from __future__ import annotations

from pathlib import Path

import pytest
from cheese_flow.lib.model_manifest import (
    ModelManifest,
    apply_model_manifest,
    read_model_manifest,
)


def test_returns_none_when_models_yaml_is_absent(tmp_path: Path) -> None:
    assert read_model_manifest(tmp_path) is None


def test_parses_pins_and_overrides(tmp_path: Path) -> None:
    (tmp_path / "models.yaml").write_text(
        "\n".join(
            [
                "pins:",
                "  claude-code:",
                "    sonnet: claude-sonnet-4-6",
                "    opus: claude-opus-4-7",
                "  codex:",
                "    gpt-5-codex: gpt-5.3-codex",
                "overrides:",
                "  age-correctness:",
                "    claude-code: claude-opus-4-7",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest = read_model_manifest(tmp_path)
    assert manifest is not None
    assert manifest.pins is not None
    assert manifest.pins.get("claude-code") == {
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-7",
    }
    assert manifest.pins.get("codex") == {"gpt-5-codex": "gpt-5.3-codex"}
    assert manifest.overrides is not None
    assert manifest.overrides["age-correctness"].get("claude-code") == "claude-opus-4-7"


def test_rejects_unknown_harness_keys_via_strict_schema(tmp_path: Path) -> None:
    (tmp_path / "models.yaml").write_text(
        "pins:\n  qwen-code:\n    sonnet: foo\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        read_model_manifest(tmp_path)


def test_treats_an_empty_file_as_an_empty_manifest(tmp_path: Path) -> None:
    (tmp_path / "models.yaml").write_text("", encoding="utf-8")
    manifest = read_model_manifest(tmp_path)
    assert manifest is not None
    assert manifest.pins is None
    assert manifest.overrides is None


def test_propagates_non_enoent_read_errors(tmp_path: Path) -> None:
    (tmp_path / "models.yaml").mkdir()
    with pytest.raises((ValueError, IsADirectoryError, PermissionError)):
        read_model_manifest(tmp_path)


_BASE_INPUT = {
    "model": "sonnet",
    "agent_name": "age-correctness",
    "harness": "claude-code",
}


def test_returns_input_model_when_manifest_is_none() -> None:
    assert apply_model_manifest(**_BASE_INPUT, manifest=None) == "sonnet"  # type: ignore[arg-type]


def test_returns_input_model_when_no_pin_or_override_matches() -> None:
    manifest = ModelManifest.model_validate({"pins": {"codex": {"gpt-5-codex": "gpt-5.3-codex"}}})
    assert apply_model_manifest(**_BASE_INPUT, manifest=manifest) == "sonnet"  # type: ignore[arg-type]


def test_substitutes_pinned_version_when_alias_matches_harness_pin() -> None:
    manifest = ModelManifest.model_validate(
        {"pins": {"claude-code": {"sonnet": "claude-sonnet-4-6"}}}
    )
    assert (
        apply_model_manifest(**_BASE_INPUT, manifest=manifest)  # type: ignore[arg-type]
        == "claude-sonnet-4-6"
    )


def test_uses_override_that_supersedes_any_matching_pin() -> None:
    manifest = ModelManifest.model_validate(
        {
            "pins": {"claude-code": {"sonnet": "claude-sonnet-4-6"}},
            "overrides": {"age-correctness": {"claude-code": "claude-opus-4-7"}},
        }
    )
    assert (
        apply_model_manifest(**_BASE_INPUT, manifest=manifest)  # type: ignore[arg-type]
        == "claude-opus-4-7"
    )


def test_ignores_overrides_for_a_different_agent() -> None:
    manifest = ModelManifest.model_validate(
        {"overrides": {"age-security": {"claude-code": "claude-opus-4-7"}}}
    )
    assert apply_model_manifest(**_BASE_INPUT, manifest=manifest) == "sonnet"  # type: ignore[arg-type]


def test_ignores_pins_for_a_different_harness() -> None:
    manifest = ModelManifest.model_validate({"pins": {"codex": {"sonnet": "gpt-5.5"}}})
    assert apply_model_manifest(**_BASE_INPUT, manifest=manifest) == "sonnet"  # type: ignore[arg-type]
