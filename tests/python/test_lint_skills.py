"""Verbatim port of `tests/lint-skills-directory.test.ts`.

Mirrors the vitest cases for ``lint_skills_directory``, ``format_lint_report``,
and ``has_errors``. The directory-as-SKILL.md trick from the TS suite (forces
``readFile`` to fail with EISDIR) maps cleanly to the Python read_text branch
which raises ``IsADirectoryError`` (a subclass of ``OSError``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from pathlib import Path

from cheese_flow.lib.harness_compat import HarnessCompatFinding
from cheese_flow.lib.lint_skills import (
    format_lint_report,
    has_errors,
    lint_skills_directory,
)

VALID_BODY = "# Skill body\n\nUse this skill to do a thing.\n"


def _write_skill(skills_root: Path, directory_name: str, contents: str) -> None:
    target = skills_root / directory_name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(contents, encoding="utf8")


def _run(coro: Awaitable[object]):
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_reports_skill_md_is_required_when_missing(tmp_path: Path) -> None:
    (tmp_path / "empty-skill").mkdir()

    report = _run(lint_skills_directory(str(tmp_path)))

    assert report["scanned"] == 1
    assert len(report["issues"]) == 1
    assert report["issues"][0]["rule"] == "skill-md-required"
    assert has_errors(report) is True


def test_reports_skill_md_unreadable_when_skill_md_exists_but_cannot_be_read(
    tmp_path: Path,
) -> None:
    (tmp_path / "unreadable-skill" / "SKILL.md").mkdir(parents=True)

    report = _run(lint_skills_directory(str(tmp_path)))

    assert report["scanned"] == 1
    assert len(report["issues"]) == 1
    assert report["issues"][0]["rule"] == "skill-md-unreadable"
    assert "SKILL.md could not be read" in report["issues"][0]["message"]
    assert has_errors(report) is True


def test_returns_a_clean_report_when_all_skills_validate(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "good-skill",
        (
            "---\nname: good-skill\ndescription: A perfectly fine description "
            "that is long enough for discovery.\n---\n" + VALID_BODY
        ),
    )

    report = _run(lint_skills_directory(str(tmp_path)))

    assert report["scanned"] == 1
    assert report["issues"] == []
    assert has_errors(report) is False


def test_runs_compile_test_against_harness_adapters_with_emit_surface(
    tmp_path: Path,
) -> None:
    _write_skill(
        tmp_path,
        "good-skill",
        (
            "---\nname: good-skill\ndescription: A perfectly fine description "
            "that is long enough for discovery.\n---\n" + VALID_BODY
        ),
    )

    report = _run(lint_skills_directory(str(tmp_path)))

    assert not any(entry["rule"].startswith("compile-") for entry in report["issues"])


def test_skips_compile_test_when_source_has_errors(tmp_path: Path) -> None:
    # Malformed YAML causes a frontmatter-parse source error. The early
    # return in lint_skill_directory should prevent compile-test from running,
    # so only the source error is reported (not duplicate adapter failures).
    _write_skill(
        tmp_path,
        "bad-yaml",
        (
            "---\nname: bad-yaml\ndescription: A perfectly fine description "
            "that is long enough for discovery.\n"
            "allowed-tools: { unclosed: brace\n---\n" + VALID_BODY
        ),
    )

    report = _run(lint_skills_directory(str(tmp_path)))

    error_finding = next(
        (entry for entry in report["issues"] if entry["severity"] == "error"),
        None,
    )
    assert error_finding is not None
    assert error_finding["severity"] == "error"
    assert not any(entry["rule"].startswith("compile-") for entry in report["issues"])


def test_returns_no_issues_when_source_is_clean_and_every_adapter_compiles(
    tmp_path: Path,
) -> None:
    _write_skill(
        tmp_path,
        "good-skill",
        (
            "---\nname: good-skill\ndescription: A perfectly fine description "
            "that is long enough for discovery.\n---\n" + VALID_BODY
        ),
    )
    report = _run(lint_skills_directory(str(tmp_path)))
    assert report["issues"] == []


def test_format_lint_report_reports_a_clean_run_when_issues_are_empty() -> None:
    text = format_lint_report({"scanned": 1, "issues": []})
    assert "1 skill scanned" in text
    assert "No issues found." in text


def test_format_lint_report_anchors_body_findings_with_file_line() -> None:
    text = format_lint_report(
        {
            "scanned": 1,
            "issues": [
                {
                    "skill": "x",
                    "file": "x/SKILL.md",
                    "severity": "warning",
                    "rule": "body-claude-only-tool",
                    "message": "agent-only",
                    "line": 42,
                }
            ],
        }
    )
    assert "x/SKILL.md:42" in text


def test_converts_compile_trip_findings_into_lint_issues_when_source_is_clean(
    tmp_path: Path,
) -> None:
    _write_skill(
        tmp_path,
        "clean-skill",
        (
            "---\nname: clean-skill\ndescription: A perfectly fine description "
            "that is long enough for discovery.\n---\n" + VALID_BODY
        ),
    )

    async def fake_compile(
        _name: str, _source: str
    ) -> list[HarnessCompatFinding]:
        return [
            {
                "rule": "compile-cursor-failed",
                "severity": "error",
                "message": "synthetic adapter failure",
            },
            {
                "rule": "compile-codex-warned",
                "severity": "warning",
                "message": "synthetic adapter warning at body line 3",
                "line": 3,
            },
        ]

    report = _run(lint_skills_directory(str(tmp_path), {"compile": fake_compile}))

    compile_issue = next(
        (entry for entry in report["issues"] if entry["rule"] == "compile-cursor-failed"),
        None,
    )
    assert compile_issue is not None
    assert compile_issue["severity"] == "error"
    assert "synthetic adapter failure" in compile_issue["message"]
    assert compile_issue["skill"] == "clean-skill"
    assert compile_issue.get("line") is None

    lined_issue = next(
        (entry for entry in report["issues"] if entry["rule"] == "compile-codex-warned"),
        None,
    )
    assert lined_issue is not None
    assert lined_issue.get("line") == 3


def test_emits_skill_md_unreadable_when_skill_md_is_a_directory(tmp_path: Path) -> None:
    # Sibling skill with a regular SKILL.md — should produce no issues.
    blocked_dir = tmp_path / "blocked-skill"
    blocked_dir.mkdir()
    (blocked_dir / "SKILL.md").write_text("ok\n", encoding="utf8")
    # Force read_text(EISDIR) by making SKILL.md a directory. stat() succeeds
    # (it's a real entry), but read_text raises IsADirectoryError —
    # exercising the non-FileNotFoundError branch in the SKILL.md loader.
    (tmp_path / "dir-as-file" / "SKILL.md").mkdir(parents=True)

    report = _run(lint_skills_directory(str(tmp_path)))
    unreadable_finding = next(
        (entry for entry in report["issues"] if entry["rule"] == "skill-md-unreadable"),
        None,
    )
    assert unreadable_finding is not None
    assert unreadable_finding["severity"] == "error"
    assert unreadable_finding["skill"] == "dir-as-file"


def test_format_lint_report_summarizes_counts() -> None:
    text = format_lint_report(
        {
            "scanned": 2,
            "issues": [
                {
                    "skill": "a",
                    "file": "a/SKILL.md",
                    "severity": "error",
                    "rule": "frontmatter:name",
                    "message": "bad",
                },
                {
                    "skill": "b",
                    "file": "b/SKILL.md",
                    "severity": "warning",
                    "rule": "body-too-long",
                    "message": "long",
                },
            ],
        }
    )
    assert "2 skills scanned" in text
    assert "[ERROR]" in text
    assert "[WARN]" in text
    assert "1 error(s), 1 warning(s)" in text
