"""Port of ``tests/cheese-dir.test.ts``.

Asserts the ``CHEESE_DIR`` constant, ``bootstrapHook`` capability flags,
``<harness>/`` placeholder absence in shipped commands/skills, the
``body-harness-placeholder`` lint rule, and the ``.gitignore`` / repo-root
``hooks.json`` shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.harness import CHEESE_DIR
from cheese_flow.lib.harness_compat import check_body_harness_idioms

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_markdown_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    collected: list[Path] = []
    for entry in directory.iterdir():
        if entry.is_dir():
            collected.extend(_read_markdown_files(entry))
        elif entry.is_file() and entry.suffix == ".md":
            collected.append(entry)
    return collected


# ─── AC1: CHEESE_DIR constant ────────────────────────────────────────────────


def test_cheese_dir_is_dot_cheese() -> None:
    assert CHEESE_DIR == ".cheese"


# ─── AC2: bootstrapHook capability flag ──────────────────────────────────────


def test_every_adapter_exposes_bootstrap_hook_as_bool() -> None:
    for name, adapter in HARNESS_ADAPTERS.items():
        flag = adapter.capabilities.bootstrapHook
        assert isinstance(flag, bool), (
            f"adapter {name} must expose capabilities.bootstrapHook as bool"
        )


def test_bootstrap_hook_enabled_for_claude_codex_copilot() -> None:
    assert HARNESS_ADAPTERS["claude-code"].capabilities.bootstrapHook is True
    assert HARNESS_ADAPTERS["codex"].capabilities.bootstrapHook is True
    assert HARNESS_ADAPTERS["copilot-cli"].capabilities.bootstrapHook is True


def test_bootstrap_hook_disabled_for_cursor() -> None:
    assert HARNESS_ADAPTERS["cursor"].capabilities.bootstrapHook is False


# ─── AC3: <harness>/ placeholder removal ─────────────────────────────────────


def test_no_harness_placeholder_in_commands_or_skills() -> None:
    files = _read_markdown_files(REPO_ROOT / "commands") + _read_markdown_files(
        REPO_ROOT / "skills"
    )
    assert len(files) > 0
    offenders = [
        str(file.relative_to(REPO_ROOT))
        for file in files
        if "<harness>/" in file.read_text(encoding="utf-8")
    ]
    assert offenders == [], f'files still containing "<harness>/": {", ".join(offenders)}'


# ─── AC4: body-harness-placeholder lint rule ─────────────────────────────────


def test_body_harness_placeholder_flags_harness_path() -> None:
    findings = check_body_harness_idioms("This writes to `<harness>/specs/foo.md`")
    placeholder = [f for f in findings if f["rule"] == "body-harness-placeholder"]
    assert len(placeholder) >= 1
    assert placeholder[0]["severity"] == "error"


def test_body_harness_placeholder_does_not_flag_dot_cheese_path() -> None:
    findings = check_body_harness_idioms("This writes to `.cheese/specs/foo.md`")
    placeholder = [f for f in findings if f["rule"] == "body-harness-placeholder"]
    assert placeholder == []


def test_body_harness_placeholder_message_contains_dot_cheese_replacement() -> None:
    findings = check_body_harness_idioms("This writes to `<harness>/research/foo.md`")
    placeholder = [f for f in findings if f["rule"] == "body-harness-placeholder"]
    assert len(placeholder) >= 1
    assert ".cheese/" in placeholder[0]["message"]


# ─── AC6: .gitignore contains .cheese/ ───────────────────────────────────────


def test_gitignore_contains_dot_cheese_line() -> None:
    body = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".cheese/" in body.splitlines()


# ─── AC5: project-root hooks.json registers cheese-bootstrap.sh ──────────────


def test_repo_hooks_json_exists() -> None:
    hooks_path = REPO_ROOT / "hooks.json"
    assert hooks_path.is_file()


def test_repo_hooks_json_registers_cheese_bootstrap_on_session_start() -> None:
    parsed = json.loads((REPO_ROOT / "hooks.json").read_text(encoding="utf-8"))
    hooks_root = parsed.get("hooks", parsed)
    session_start = hooks_root.get("sessionStart")
    assert isinstance(session_start, list)
    assert len(session_start) >= 1
    references_script = any(
        isinstance(entry.get("command"), str) and "cheese-bootstrap.sh" in entry["command"]
        for entry in session_start
    )
    assert references_script, "expected sessionStart entry to reference cheese-bootstrap.sh"
