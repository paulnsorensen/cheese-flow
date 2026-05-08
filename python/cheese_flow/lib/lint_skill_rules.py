"""Port of `src/lib/lint-skill-rules.ts` — skill linter rule library.

Mirrors the TS surface: ``lint_skill_source``, ``make_issue_factory``, and the
``LintIssue`` / ``LintSeverity`` / ``IssueFactory`` / ``LintSourceContext``
types. Behavior parity with the TS module is the bar.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal, TypedDict

from pydantic import ValidationError

from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.harness_compat import (
    check_allowed_tools_portability,
    check_body_harness_idioms,
    check_frontmatter_portability,
)
from cheese_flow.lib.schemas import parse_skill_frontmatter

LintSeverity = Literal["error", "warning"]


class _LintIssueRequired(TypedDict):
    skill: str
    file: str
    severity: LintSeverity
    rule: str
    message: str


class LintIssue(_LintIssueRequired, total=False):
    line: int


IssueFactory = Callable[..., LintIssue]


class LintSourceContext(TypedDict):
    directoryName: str
    relativeFile: str
    source: str


_RECOMMENDED_BODY_LINE_LIMIT = 500
_MIN_DESCRIPTION_LENGTH = 20

_BODY_OFFSET_PATTERN = re.compile(r"\r?\n---\r?\n")
_LINE_SPLIT_PATTERN = re.compile(r"\r?\n")


def make_issue_factory(directory_name: str, relative_file: str) -> IssueFactory:
    def factory(
        severity: LintSeverity,
        rule: str,
        message: str,
        line: int | None = None,
    ) -> LintIssue:
        issue: LintIssue = {
            "skill": directory_name,
            "file": relative_file,
            "severity": severity,
            "rule": rule,
            "message": message,
        }
        if line is not None:
            issue["line"] = line
        return issue

    return factory


def lint_skill_source(context: LintSourceContext) -> list[LintIssue]:
    issue = make_issue_factory(context["directoryName"], context["relativeFile"])

    try:
        data, body = parse_frontmatter(context["source"])
    except Exception as error:  # noqa: BLE001 - mirror TS catch
        return [issue("error", "frontmatter-parse", str(error))]

    issues: list[LintIssue] = []
    issues.extend(_validate_frontmatter(data, context, issue))
    issues.extend(_validate_body(body, _body_line_offset(context["source"]), issue))
    return issues


def _body_line_offset(source: str) -> int:
    match = _BODY_OFFSET_PATTERN.search(source)
    if match is None:
        return 0
    lead = source[: match.start()]
    header_lines = len(_LINE_SPLIT_PATTERN.split(lead))
    return header_lines + 1


def _validate_frontmatter(
    data: object,
    context: LintSourceContext,
    issue: IssueFactory,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    frontmatter = _try_parse_frontmatter(data, issue, issues)

    if frontmatter is not None:
        issues.extend(_name_and_description_checks(frontmatter, context, issue))

    if isinstance(data, dict):
        raw = dict(data)
        issues.extend(_portability_checks(raw.get("allowed-tools"), raw, issue))

    return issues


def _try_parse_frontmatter(
    data: object,
    issue: IssueFactory,
    issues: list[LintIssue],
):
    try:
        return parse_skill_frontmatter(data)
    except ValidationError as error:
        _push_pydantic_issues(error, issue, issues)
        return None
    except Exception as error:  # noqa: BLE001 - mirror TS catch
        issues.append(issue("error", "frontmatter-parse", str(error)))
        return None


def _push_pydantic_issues(
    error: ValidationError,
    issue: IssueFactory,
    issues: list[LintIssue],
) -> None:
    for entry in error.errors():
        location = entry.get("loc", ())
        field_path = ".".join(str(part) for part in location) or "<frontmatter>"
        message = entry.get("msg", "")
        issues.append(
            issue(
                "error",
                f"frontmatter:{field_path}",
                f"{field_path}: {message}",
            )
        )


def _name_and_description_checks(
    frontmatter,
    context: LintSourceContext,
    issue: IssueFactory,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    if frontmatter.name != context["directoryName"]:
        issues.append(
            issue(
                "error",
                "name-matches-directory",
                f'frontmatter name "{frontmatter.name}" must match parent '
                f'directory "{context["directoryName"]}".',
            )
        )

    description = frontmatter.description.strip()
    if len(description) < _MIN_DESCRIPTION_LENGTH:
        issues.append(
            issue(
                "warning",
                "description-too-short",
                f"description is {len(description)} chars; aim for at least "
                f"{_MIN_DESCRIPTION_LENGTH} so agents can match it during "
                "discovery.",
            )
        )
    return issues


def _portability_checks(
    allowed_tools: object,
    raw_frontmatter: dict[str, object],
    issue: IssueFactory,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    allowed: str | list[str] | None = (
        allowed_tools if isinstance(allowed_tools, (str, list)) else None
    )

    for finding in check_allowed_tools_portability(allowed):
        issues.append(issue(finding["severity"], finding["rule"], finding["message"]))
    for finding in check_frontmatter_portability(raw_frontmatter, "skill"):
        issues.append(issue(finding["severity"], finding["rule"], finding["message"]))
    return issues


def _validate_body(
    body: str,
    line_offset: int,
    issue: IssueFactory,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    body_line_count = len(_LINE_SPLIT_PATTERN.split(body))
    if body_line_count > _RECOMMENDED_BODY_LINE_LIMIT:
        issues.append(
            issue(
                "warning",
                "body-too-long",
                f"SKILL.md body is {body_line_count} lines; the spec "
                f"recommends staying under {_RECOMMENDED_BODY_LINE_LIMIT}. "
                "Move detail into references/.",
            )
        )
    for finding in check_body_harness_idioms(body):
        finding_line = finding.get("line")
        absolute_line = (
            finding_line + line_offset if finding_line is not None else None
        )
        issues.append(
            issue(
                finding["severity"],
                finding["rule"],
                finding["message"],
                absolute_line,
            )
        )
    return issues


__all__ = [
    "IssueFactory",
    "LintIssue",
    "LintSeverity",
    "LintSourceContext",
    "lint_skill_source",
    "make_issue_factory",
]
