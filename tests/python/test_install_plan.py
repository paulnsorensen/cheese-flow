"""Verbatim port of `tests/install-plan.test.ts`.

The TS test surface uses async closures over `Set<string>` to mock the
filesystem/PATH probes. Python keeps the async signatures so the tests use
`asyncio.run` per the convention established in `test_compiler.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from cheese_flow.lib.harness_detection import HarnessDetectionEnvironment
from cheese_flow.lib.install_plan import (
    HarnessInstallPlan,
    HarnessInstallPlanEntry,
    create_harness_install_plan,
    find_command_on_path,
    has_directory,
    parse_harness_overrides,
)


def _make_environment(
    *,
    commands: list[str] | None = None,
    surfaces: list[str] | None = None,
) -> HarnessDetectionEnvironment:
    command_set = set(commands or [])
    surface_set = set(surfaces or [])

    async def find_command(command: str) -> str | None:
        if command in command_set:
            return str(Path("/mock/bin") / command)
        return None

    async def check_directory(directory_path: str) -> bool:
        return directory_path in surface_set

    return HarnessDetectionEnvironment(findCommand=find_command, hasDirectory=check_directory)


def _get_entry(plan: HarnessInstallPlan, harness: str) -> HarnessInstallPlanEntry:
    for candidate in plan["entries"]:
        if candidate["harness"] == harness:
            return candidate
    raise AssertionError(f"Missing plan entry for {harness}")


def test_find_command_on_path_finds_commands_already_on_path() -> None:
    result = asyncio.run(find_command_on_path("node"))
    assert isinstance(result, str)
    assert len(result) > 0


def test_has_directory_detects_directories_on_disk() -> None:
    src_path = str(Path("src").resolve())
    missing_path = str(Path("missing-install-plan-directory").resolve())
    assert asyncio.run(has_directory(src_path)) is True
    assert asyncio.run(has_directory(missing_path)) is False


def test_create_plan_auto_detects_a_single_manual_capable_harness_from_its_cli() -> None:
    plan = asyncio.run(
        create_harness_install_plan(
            project_root="/workspace",
            environment=_make_environment(commands=["claude"]),
        )
    )

    assert plan["selectionMode"] == "auto-detect"
    assert plan["ok"] is True
    assert plan["selectedHarnesses"] == ["claude-code"]

    claude_entry = _get_entry(plan, "claude-code")
    assert claude_entry["selection"] == "selected"
    assert claude_entry["capability"] == "manual-capable"
    assert claude_entry["detection"] == {
        "state": "detected",
        "kind": "cli",
        "value": str(Path("/mock/bin") / "claude"),
        "reason": claude_entry["detection"]["reason"],
    }
    assert _get_entry(plan, "codex")["selection"] == "skipped"


def test_create_plan_auto_detects_multiple_harnesses_from_cli_and_project_surfaces() -> None:
    project_root = "/workspace"
    plan = asyncio.run(
        create_harness_install_plan(
            project_root=project_root,
            environment=_make_environment(
                commands=["copilot"],
                surfaces=[str(Path(project_root) / ".cursor")],
            ),
        )
    )

    assert plan["selectionMode"] == "auto-detect"
    assert plan["ok"] is True
    assert plan["selectedHarnesses"] == ["cursor", "copilot-cli"]

    cursor_entry = _get_entry(plan, "cursor")
    assert cursor_entry["selection"] == "selected"
    assert cursor_entry["capability"] == "auto-install"
    assert cursor_entry["detection"]["state"] == "detected"
    assert cursor_entry["detection"]["kind"] == "surface"
    assert cursor_entry["detection"]["value"] == str(Path(project_root) / ".cursor")

    copilot_entry = _get_entry(plan, "copilot-cli")
    assert copilot_entry["selection"] == "selected"
    assert copilot_entry["capability"] == "auto-install"
    assert copilot_entry["detection"]["state"] == "detected"
    assert copilot_entry["detection"]["kind"] == "cli"
    assert copilot_entry["detection"]["value"] == str(Path("/mock/bin") / "copilot")


def test_create_plan_preserves_explicit_harness_order_after_dedupe_bypasses_auto_detect() -> None:
    requested_harnesses = parse_harness_overrides(
        ["copilot-cli,cursor", "copilot-cli", "claude-code,cursor"]
    )
    plan = asyncio.run(
        create_harness_install_plan(
            project_root="/workspace",
            requested_harnesses=requested_harnesses,
            environment=_make_environment(commands=["codex"]),
        )
    )

    assert requested_harnesses == ["copilot-cli", "cursor", "claude-code"]
    assert plan["selectionMode"] == "explicit"
    assert plan["ok"] is True
    assert plan["selectedHarnesses"] == requested_harnesses

    copilot_entry = _get_entry(plan, "copilot-cli")
    assert copilot_entry["selection"] == "selected"
    assert copilot_entry["capability"] == "auto-install"
    assert copilot_entry["detection"]["state"] == "bypassed"

    claude_entry = _get_entry(plan, "claude-code")
    assert claude_entry["selection"] == "selected"
    assert claude_entry["capability"] == "manual-capable"
    assert claude_entry["detection"]["state"] == "bypassed"

    codex_entry = _get_entry(plan, "codex")
    assert codex_entry["selection"] == "skipped"
    assert codex_entry["detection"]["state"] == "bypassed"


def test_create_plan_returns_guidance_when_auto_detect_finds_no_harnesses() -> None:
    plan = asyncio.run(
        create_harness_install_plan(
            project_root="/workspace",
            environment=_make_environment(),
        )
    )

    assert plan["selectionMode"] == "auto-detect"
    assert plan["ok"] is False
    assert plan["selectedHarnesses"] == []
    guidance = plan.get("guidance", "")
    assert "--harness <name>" in guidance
    assert "cheese compile" in guidance
    assert all(entry["selection"] == "skipped" for entry in plan["entries"])


def test_parse_harness_overrides_rejects_unsupported_harness_names() -> None:
    with pytest.raises(ValueError, match="Unsupported harness"):
        parse_harness_overrides(["bogus"])
