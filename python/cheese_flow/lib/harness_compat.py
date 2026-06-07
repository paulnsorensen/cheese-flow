"""Port of `src/lib/harness-compat.ts` — harness portability findings.

Mirrors the TS surface: ``check_allowed_tools_portability``,
``check_frontmatter_portability``, ``check_body_harness_idioms``, and
``compile_test_skill``. All findings are emitted as ``HarnessCompatFinding``
TypedDicts with the same ``rule`` / ``severity`` / ``message`` / ``line``
fields as the TS module.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypedDict

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.capabilities import event_support, field_support, tool_support
from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.harness import HarnessAdapter, HarnessName
from cheese_flow.lib.schemas import parse_skill_frontmatter

Severity = Literal["error", "warning"]


class _HarnessCompatFindingRequired(TypedDict):
    rule: str
    severity: Severity
    message: str


class HarnessCompatFinding(_HarnessCompatFindingRequired, total=False):
    line: int


_CLAUDE_PERMISSION_GLOB = re.compile(r"\b([A-Za-z]\w*)\(([^)]*:[^)]*)\)")

_HARNESS_PATH_MARKERS: tuple[str, ...] = (
    ".claude/",
    ".claude-plugin/",
    ".codex/",
    ".cursor/",
    ".copilot/",
    "AGENTS.md",
    "copilot-instructions.md",
)


def _display_name(harness: HarnessName) -> str:
    return HARNESS_ADAPTERS[harness].displayName


def check_allowed_tools_portability(
    allowed_tools: str | list[str] | None,
) -> list[HarnessCompatFinding]:
    if allowed_tools is None:
        return []
    text = ", ".join(allowed_tools) if isinstance(allowed_tools, list) else allowed_tools
    matches = list(_CLAUDE_PERMISSION_GLOB.finditer(text))
    if not matches:
        return []
    return [
        {
            "rule": "allowed-tools-claude-permission-syntax",
            "severity": "warning",
            "message": (
                f'allowed-tools entry "{match.group(0)}" uses Claude Code '
                "permission-glob syntax; Cursor, Codex, and Copilot CLI do not "
                'parse it. Drop the "(...:...)" suffix or list bare tool names '
                "for portability."
            ),
        }
        for match in matches
    ]


def check_frontmatter_portability(
    frontmatter: dict[str, object],
    kind: Literal["skill", "agent"],
) -> list[HarnessCompatFinding]:
    support = field_support(kind)
    all_adapters: list[HarnessName] = list(HARNESS_ADAPTERS.keys())
    findings: list[HarnessCompatFinding] = []

    for key, supported_by in support.items():
        if frontmatter.get(key) is None:
            continue
        if len(supported_by) == len(all_adapters):
            continue
        if key == "context" and frontmatter[key] == "inline":
            continue

        unsupported: list[HarnessName] = [n for n in all_adapters if n not in supported_by]
        supported_names = ", ".join(_display_name(n) for n in supported_by)
        unsupported_names = ", ".join(_display_name(n) for n in unsupported)
        findings.append(
            {
                "rule": "frontmatter-portability",
                "severity": "warning",
                "message": (
                    f'frontmatter field "{key}" is supported only by '
                    f"{supported_names}; {unsupported_names} drop it. Move the "
                    "constraint into the body, or accept the field will be "
                    "ignored."
                ),
            }
        )
    return findings


def _line_number_of(source: str, index: int) -> int:
    return source[: min(index, len(source))].count("\n") + 1


def _find_first_match_line(body: str, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(body)
    if match is None:
        return None
    return _line_number_of(body, match.start())


def check_body_harness_idioms(body: str) -> list[HarnessCompatFinding]:
    return [
        *_collect_tool_findings(body),
        *_collect_event_findings(body),
        *_collect_path_findings(body),
        *_collect_placeholder_findings(body),
    ]


def _collect_placeholder_findings(body: str) -> list[HarnessCompatFinding]:
    line = _find_first_match_line(body, re.compile(r"<harness>/"))
    if line is None:
        return []
    return [
        {
            "rule": "body-harness-placeholder",
            "severity": "error",
            "message": (
                'body uses the "<harness>/" placeholder; replace with '
                '".cheese/" so all four harnesses share a single project-root '
                "runtime directory."
            ),
            "line": line,
        }
    ]


def _collect_tool_findings(body: str) -> list[HarnessCompatFinding]:
    all_adapters: list[HarnessName] = list(HARNESS_ADAPTERS.keys())
    findings: list[HarnessCompatFinding] = []
    for tool, supported_by in tool_support().items():
        line = _find_first_match_line(body, re.compile(rf"\b{re.escape(tool)}\("))
        if line is None:
            continue
        unsupported_names = ", ".join(
            _display_name(n) for n in all_adapters if n not in supported_by
        )
        findings.append(
            {
                "rule": "body-claude-only-tool",
                "severity": "warning",
                "message": (
                    f'body references tool "{tool}(...)"; {unsupported_names} '
                    "do not expose this tool. Rephrase generically (e.g. "
                    '"spawn a sub-agent").'
                ),
                "line": line,
            }
        )
    return findings


def _collect_event_findings(body: str) -> list[HarnessCompatFinding]:
    all_adapters: list[HarnessName] = list(HARNESS_ADAPTERS.keys())
    hook_adapter_count = sum(
        1 for n in all_adapters if len(HARNESS_ADAPTERS[n].capabilities.hookEvents) > 0
    )
    findings: list[HarnessCompatFinding] = []
    for camel_event, supported_by in event_support().items():
        pascal_event = camel_event[:1].upper() + camel_event[1:]
        line = _find_first_match_line(body, re.compile(rf"\b{re.escape(pascal_event)}\b"))
        if line is None:
            continue
        findings.append(
            _event_finding(
                camel_event,
                pascal_event,
                supported_by,
                hook_adapter_count,
                all_adapters,
                line,
            )
        )
    return findings


def _event_finding(
    camel_event: str,
    pascal_event: str,
    supported_by: list[HarnessName],
    hook_adapter_count: int,
    all_adapters: list[HarnessName],
    line: int,
) -> HarnessCompatFinding:
    if len(supported_by) == hook_adapter_count:
        return {
            "rule": "body-pascal-hook-event",
            "severity": "warning",
            "message": (
                f'body references PascalCase hook event "{pascal_event}"; '
                "cheese-flow's portable hooks use camelCase "
                f'("{camel_event}"). Per-harness mapping is applied at '
                "compile time."
            ),
            "line": line,
        }
    unsupported: list[HarnessName] = [n for n in all_adapters if n not in supported_by]
    supported_names = ", ".join(_display_name(n) for n in supported_by)
    unsupported_names = ", ".join(_display_name(n) for n in unsupported)
    return {
        "rule": "body-harness-only-hook-event",
        "severity": "warning",
        "message": (
            f'body references hook event "{pascal_event}" which is supported '
            f"only by {supported_names}; {unsupported_names} do not expose it."
        ),
        "line": line,
    }


def _collect_path_findings(body: str) -> list[HarnessCompatFinding]:
    findings: list[HarnessCompatFinding] = []
    for marker in _HARNESS_PATH_MARKERS:
        line = _find_first_match_line(body, re.compile(re.escape(marker)))
        if line is None:
            continue
        findings.append(
            {
                "rule": "body-harness-path-marker",
                "severity": "warning",
                "message": (
                    f'body references harness-specific path "{marker}"; '
                    "portable skills should use the cheese-flow source layout "
                    '(e.g. "skills/<name>/SKILL.md") and let adapters project '
                    "per harness."
                ),
                "line": line,
            }
        )
    return findings


async def _setup_skill_dir(tmp_root: Path, skill_name: str, skill_source: str) -> Path:
    skills_dir = tmp_root / "skills"
    skill_dir = skills_dir / skill_name
    await asyncio.to_thread(skill_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread((skill_dir / "SKILL.md").write_text, skill_source, encoding="utf8")
    return skills_dir


async def _try_adapter_install(
    adapter: HarnessAdapter,
    skills_dir: Path,
    tmp_root: Path,
) -> HarnessCompatFinding | None:
    output_root = tmp_root / adapter.outputRoot
    skill_output_root = output_root / adapter.skillDirectory
    try:
        await asyncio.to_thread(skill_output_root.mkdir, parents=True, exist_ok=True)
        await _simulate_copy_skills(skills_dir, skill_output_root)
        if adapter.emitSurface is not None:
            await adapter.emitSurface(str(skills_dir), str(output_root))
        return None
    except Exception as error:  # noqa: BLE001 - mirror TS catch
        return {
            "rule": f"compile-{adapter.name}-failed",
            "severity": "error",
            "message": (f"{adapter.displayName} adapter failed to emit: {error}"),
        }


async def _simulate_copy_skills(skills_dir: Path, skill_output_root: Path) -> None:
    entries = await asyncio.to_thread(_list_directories, skills_dir)
    for entry in entries:
        skill_readme_path = entry / "SKILL.md"
        content = await asyncio.to_thread(skill_readme_path.read_text, encoding="utf8")
        parsed_data, _ = parse_frontmatter(content)
        frontmatter = parse_skill_frontmatter(parsed_data)
        if frontmatter.name != entry.name:
            raise ValueError(
                f'Skill directory "{entry.name}" must match frontmatter name "{frontmatter.name}".'
            )
        destination = skill_output_root / entry.name
        await asyncio.to_thread(_copy_tree_force, entry, destination)


def _list_directories(skills_dir: Path) -> list[Path]:
    return [child for child in skills_dir.iterdir() if child.is_dir()]


def _copy_tree_force(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


async def compile_test_skill(skill_name: str, skill_source: str) -> list[HarnessCompatFinding]:
    findings: list[HarnessCompatFinding] = []
    tmp_root = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="cheese-compile-"))
    try:
        skills_dir = await _setup_skill_dir(tmp_root, skill_name, skill_source)
        for adapter in _ordered_adapters():
            finding = await _try_adapter_install(adapter, skills_dir, tmp_root)
            if finding is not None:
                findings.append(finding)
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp_root, ignore_errors=True)
    return findings


def _ordered_adapters() -> Iterable[HarnessAdapter]:
    return list(HARNESS_ADAPTERS.values())


__all__ = [
    "HarnessCompatFinding",
    "check_allowed_tools_portability",
    "check_body_harness_idioms",
    "check_frontmatter_portability",
    "compile_test_skill",
]
