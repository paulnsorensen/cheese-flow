"""Port of `src/lib/lint-skills.ts` — directory-level skill linter.

Mirrors the TS surface: ``lint_skills_directory``, ``format_lint_report``,
``has_errors``, plus ``LintReport`` / ``CompileSkillFn`` /
``LintSkillsDirectoryOptions`` types. Re-exports ``LintIssue``,
``LintSeverity``, and ``lint_skill_source`` from ``lint_skill_rules``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypedDict

from cheese_flow.lib.harness_compat import HarnessCompatFinding, compile_test_skill
from cheese_flow.lib.lint_skill_rules import (
    IssueFactory,
    LintIssue,
    LintSeverity,
    lint_skill_source,
    make_issue_factory,
)

CompileSkillFn = Callable[[str, str], Awaitable[list[HarnessCompatFinding]]]


class LintReport(TypedDict):
    scanned: int
    issues: list[LintIssue]


class LintSkillsDirectoryOptions(TypedDict, total=False):
    compile: CompileSkillFn


async def lint_skills_directory(
    skills_root: str,
    options: LintSkillsDirectoryOptions | None = None,
) -> LintReport:
    options = options or {}
    compile_fn: CompileSkillFn = options.get("compile") or compile_test_skill

    root = Path(skills_root)
    entries = await asyncio.to_thread(_list_entries, root)
    directories = sorted(entry.name for entry in entries if entry.is_dir())

    issues: list[LintIssue] = []
    for directory_name in directories:
        issues.extend(await _lint_skill_directory(skills_root, directory_name, compile_fn))
    return {"scanned": len(directories), "issues": issues}


def _list_entries(root: Path) -> list[Path]:
    return list(root.iterdir())


async def _lint_skill_directory(
    skills_root: str,
    directory_name: str,
    compile_fn: CompileSkillFn,
) -> list[LintIssue]:
    skill_file = Path(skills_root) / directory_name / "SKILL.md"
    relative_file = str(skill_file.relative_to(Path(skills_root)))
    issue = make_issue_factory(directory_name, relative_file)

    source_or_issue = await _read_skill_source(skill_file, issue)
    if "issues" in source_or_issue:
        return source_or_issue["issues"]

    source_issues = lint_skill_source(
        {
            "directoryName": directory_name,
            "relativeFile": relative_file,
            "source": source_or_issue["source"],
        }
    )

    # Skip the cross-harness compile-trip when the source itself has errors.
    # The compile step would re-surface the same parse/name failures four times,
    # one per adapter, drowning out the real source issue.
    if any(entry["severity"] == "error" for entry in source_issues):
        return source_issues

    compile_findings = await compile_fn(directory_name, source_or_issue["source"])
    compile_issues = [
        _finding_to_issue(finding, directory_name, relative_file) for finding in compile_findings
    ]

    return [*source_issues, *compile_issues]


class _SourceOk(TypedDict):
    source: str


class _SourceFailed(TypedDict):
    issues: list[LintIssue]


async def _read_skill_source(skill_file: Path, issue: IssueFactory) -> _SourceOk | _SourceFailed:
    try:
        await asyncio.to_thread(skill_file.stat)
    except FileNotFoundError:
        return {
            "issues": [
                issue(
                    "error",
                    "skill-md-required",
                    "SKILL.md is required at the skill directory root.",
                )
            ]
        }

    try:
        source = await asyncio.to_thread(skill_file.read_text, encoding="utf8")
    except Exception as error:  # noqa: BLE001 - mirror TS catch
        return {
            "issues": [
                issue(
                    "error",
                    "skill-md-unreadable",
                    f"SKILL.md could not be read: {error}",
                )
            ]
        }

    return {"source": source}


def _finding_to_issue(
    finding: HarnessCompatFinding,
    directory_name: str,
    relative_file: str,
) -> LintIssue:
    issue: LintIssue = {
        "skill": directory_name,
        "file": relative_file,
        "severity": finding["severity"],
        "rule": finding["rule"],
        "message": finding["message"],
    }
    finding_line = finding.get("line")
    if finding_line is not None:
        issue["line"] = finding_line
    return issue


def format_lint_report(report: LintReport) -> str:
    plural = "" if report["scanned"] == 1 else "s"
    lines: list[str] = [
        f"cheese lint — {report['scanned']} skill{plural} scanned",
        "",
    ]

    if not report["issues"]:
        lines.append("No issues found.")
        return "\n".join(lines) + "\n"

    for item in report["issues"]:
        tag = "ERROR" if item["severity"] == "error" else "WARN"
        item_line = item.get("line")
        anchor = f"{item['file']}:{item_line}" if item_line is not None else item["file"]
        lines.append(f"[{tag}] {anchor} ({item['rule']}): {item['message']}")

    error_count = sum(1 for entry in report["issues"] if entry["severity"] == "error")
    warning_count = len(report["issues"]) - error_count
    lines.append("")
    lines.append(f"{error_count} error(s), {warning_count} warning(s).")

    return "\n".join(lines) + "\n"


def has_errors(report: LintReport) -> bool:
    return any(item["severity"] == "error" for item in report["issues"])


__all__ = [
    "CompileSkillFn",
    "LintIssue",
    "LintReport",
    "LintSeverity",
    "LintSkillsDirectoryOptions",
    "format_lint_report",
    "has_errors",
    "lint_skill_source",
    "lint_skills_directory",
]
