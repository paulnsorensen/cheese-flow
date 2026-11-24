"""Regression tests for the cheese-flow plugin's own ``hooks.json``.

The plugin installs as a Claude Code plugin; its root ``hooks.json`` must use the
format Claude Code loads, or ``claude plugin list`` reports ``failed to load``
(issue #57). The contract: a top-level ``hooks`` map keyed by PascalCase event
names, each value a list of matcher-wrapped ``{"hooks": [{type, command}]}``
entries, with the bootstrap command rooted at ``${CLAUDE_PLUGIN_ROOT}`` so it
resolves against the installed plugin directory.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = REPO_ROOT / "hooks.json"
BOOTSTRAP_SCRIPT = REPO_ROOT / "hooks" / "cheese-bootstrap.sh"


def _load_hooks() -> dict[str, object]:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def test_hooks_json_has_top_level_hooks_map() -> None:
    document = _load_hooks()
    assert isinstance(document, dict)
    assert "hooks" in document, "hooks.json must wrap events under a top-level 'hooks' key"
    assert isinstance(document["hooks"], dict)


def test_event_names_are_pascal_case() -> None:
    events = _load_hooks()["hooks"]
    assert "SessionStart" in events, "SessionStart event must use PascalCase"
    assert "sessionStart" not in events, "camelCase 'sessionStart' is not loaded by Claude Code"


def test_entries_are_matcher_wrapped() -> None:
    for event, entries in _load_hooks()["hooks"].items():
        assert isinstance(entries, list) and entries, f"{event} must hold a non-empty list"
        for entry in entries:
            assert isinstance(entry, dict), f"{event} entry must be an object"
            inner = entry.get("hooks")
            assert isinstance(inner, list) and inner, (
                f"{event} entry must wrap commands under a 'hooks' list, not a flat command"
            )
            for command in inner:
                assert command.get("type") == "command"
                assert isinstance(command.get("command"), str) and command["command"]


def test_bootstrap_command_is_plugin_root_relative() -> None:
    inner = _load_hooks()["hooks"]["SessionStart"][0]["hooks"][0]
    command = inner["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/cheese-bootstrap.sh" in command, (
        "bootstrap command must resolve against ${CLAUDE_PLUGIN_ROOT}, not a bare relative path"
    )
    assert "bash hooks/cheese-bootstrap.sh" not in command


def test_referenced_bootstrap_script_is_present() -> None:
    assert BOOTSTRAP_SCRIPT.is_file(), (
        "the bootstrap script the hook references must ship in hooks/"
    )
