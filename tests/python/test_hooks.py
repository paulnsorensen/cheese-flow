"""Port of ``tests/hooks.test.ts`` — covers ``emit_hooks`` per-harness shape."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.emit import emit_hooks


@contextmanager
def _override_build_hook_config(harness: str, build_fn) -> Iterator[None]:  # type: ignore[no-untyped-def]
    """Swap an adapter's frozen ``buildHookConfig`` for the duration of a test."""
    original = HARNESS_ADAPTERS[harness]  # type: ignore[index]
    replaced = dataclasses.replace(original, buildHookConfig=build_fn)
    HARNESS_ADAPTERS[harness] = replaced  # type: ignore[index]
    try:
        yield
    finally:
        HARNESS_ADAPTERS[harness] = original  # type: ignore[index]


def test_skips_hook_emission_for_cursor_with_info_log(tmp_path: Path) -> None:
    source = {"sessionStart": [{"type": "command", "command": "echo start"}]}
    result = emit_hooks("cursor", source, tmp_path)
    assert result is None


def test_emits_hooks_json_with_camelcase_keys_for_claude_code(tmp_path: Path) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "echo start"}],
        "preToolUse": [{"type": "command", "command": "echo pre"}],
    }
    emit_hooks("claude-code", source, tmp_path)
    config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert "sessionStart" in config["hooks"]
    assert "preToolUse" in config["hooks"]


def test_emits_hooks_with_pascalcase_keys_for_codex(tmp_path: Path) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "echo start"}],
        "preToolUse": [{"type": "command", "command": "echo pre"}],
    }
    emit_hooks("codex", source, tmp_path)
    config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert "SessionStart" in config["hooks"]
    assert "PreToolUse" in config["hooks"]
    assert config["hooks"]["SessionStart"][0]["matcher"] is not None
    assert config["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 600


def test_emits_hooks_with_camelcase_keys_and_version_for_copilot_cli(tmp_path: Path) -> None:
    source = {"sessionStart": [{"type": "command", "command": "echo start"}]}
    emit_hooks("copilot-cli", source, tmp_path)
    config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert config["version"] == 1
    assert "sessionStart" in config["hooks"]


def test_skips_entries_that_are_explicitly_none(tmp_path: Path) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "echo start"}],
        "preToolUse": None,
    }
    emit_hooks("claude-code", source, tmp_path)  # type: ignore[arg-type]
    config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert "sessionStart" in config["hooks"]
    assert "preToolUse" not in config["hooks"]


def test_emits_session_start_bootstrap_for_every_bootstrap_hook_harness(tmp_path: Path) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "bash hooks/cheese-bootstrap.sh"}],
    }
    enabled = ("claude-code", "codex", "copilot-cli")
    for index, harness in enumerate(enabled):
        assert HARNESS_ADAPTERS[harness].capabilities.bootstrapHook is True, (
            f"{harness} must have bootstrapHook=True"
        )
        out_root = tmp_path / f"out-{index}"
        out_root.mkdir()
        result = emit_hooks(harness, source, out_root)  # type: ignore[arg-type]
        assert result is not None, f"{harness} should emit hooks.json"
        content = (out_root / "hooks.json").read_text(encoding="utf-8")
        assert "cheese-bootstrap.sh" in content


def test_places_bootstrap_command_at_structurally_correct_path_per_harness(
    tmp_path: Path,
) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "bash hooks/cheese-bootstrap.sh"}],
    }

    claude_root = tmp_path / "claude"
    claude_root.mkdir()
    emit_hooks("claude-code", source, claude_root)
    claude_config = json.loads((claude_root / "hooks.json").read_text(encoding="utf-8"))
    assert len(claude_config["hooks"]["sessionStart"]) == 1
    assert claude_config["hooks"]["sessionStart"][0]["type"] == "command"
    assert claude_config["hooks"]["sessionStart"][0]["command"] == "bash hooks/cheese-bootstrap.sh"

    codex_root = tmp_path / "codex"
    codex_root.mkdir()
    emit_hooks("codex", source, codex_root)
    codex_config = json.loads((codex_root / "hooks.json").read_text(encoding="utf-8"))
    assert len(codex_config["hooks"]["SessionStart"]) == 1
    assert codex_config["hooks"]["SessionStart"][0]["matcher"] == "*"
    assert (
        codex_config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        == "bash hooks/cheese-bootstrap.sh"
    )

    copilot_root = tmp_path / "copilot"
    copilot_root.mkdir()
    emit_hooks("copilot-cli", source, copilot_root)
    copilot_config = json.loads((copilot_root / "hooks.json").read_text(encoding="utf-8"))
    assert copilot_config["version"] == 1
    assert len(copilot_config["hooks"]["sessionStart"]) == 1
    assert (
        copilot_config["hooks"]["sessionStart"][0]["command"] == "bash hooks/cheese-bootstrap.sh"
    )


def test_skips_emission_for_cursor_when_bootstrap_hook_disabled(tmp_path: Path) -> None:
    assert HARNESS_ADAPTERS["cursor"].capabilities.bootstrapHook is False
    source = {
        "sessionStart": [{"type": "command", "command": "bash hooks/cheese-bootstrap.sh"}],
    }
    result = emit_hooks("cursor", source, tmp_path)
    assert result is None


def test_filters_bootstrap_entry_when_build_returns_payload_with_bootstrap_disabled(
    tmp_path: Path,
) -> None:
    def fake_build(portable):  # type: ignore[no-untyped-def]
        return {"hooks": portable}

    with _override_build_hook_config("cursor", fake_build):
        source = {
            "sessionStart": [
                {"type": "command", "command": "bash hooks/cheese-bootstrap.sh"},
                {"type": "command", "command": "echo other-hook"},
            ],
        }
        result = emit_hooks("cursor", source, tmp_path)
        assert result is not None
        content = (tmp_path / "hooks.json").read_text(encoding="utf-8")
        assert "cheese-bootstrap.sh" not in content
        assert "echo other-hook" in content


def test_omits_session_start_entirely_when_filter_removes_only_entry(tmp_path: Path) -> None:
    def fake_build(portable):  # type: ignore[no-untyped-def]
        return {"hooks": portable}

    with _override_build_hook_config("cursor", fake_build):
        source = {
            "sessionStart": [
                {"type": "command", "command": "bash hooks/cheese-bootstrap.sh"},
            ],
        }
        emit_hooks("cursor", source, tmp_path)
        config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
        assert "sessionStart" not in config["hooks"]


def test_skips_non_portable_events_with_warn(tmp_path: Path) -> None:
    source = {
        "sessionStart": [{"type": "command", "command": "echo start"}],
        "sessionEnd": [{"type": "command", "command": "echo end"}],
    }
    emit_hooks("claude-code", source, tmp_path)
    config = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert "sessionStart" in config["hooks"]
    assert "sessionEnd" not in config["hooks"]
