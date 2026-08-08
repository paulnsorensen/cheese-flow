"""Deterministic profile template transformations.

The profile engine receives all inputs explicitly.  In particular, rendering
never shells out to a template executable or consults the process environment;
the caller supplies the harness and (when needed) an environment snapshot.
Only the small template vocabulary used by profile MCP declarations is
supported: harness/environment lookups and ``if eq``/``if ne`` branches.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from typing import Any

_TEMPLATE_TOKEN = re.compile(r"{{(-?)(.*?)(-?)}}", re.DOTALL)


class _TemplateError(ValueError):
    """Raised internally when a template is outside the supported vocabulary."""


def needs_render(value: Any) -> bool:
    """Return whether a string contains a template expression."""

    return isinstance(value, str) and "{{" in value


def _lookup(expression: str, values: Mapping[str, str]) -> str:
    expression = expression.strip()
    if expression.startswith("$"):
        name = expression[1:]
        if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise _TemplateError(f"unsupported template variable: {expression}")
        return values.get(name, "")
    if expression.startswith("env "):
        parts = expression.split(None, 1)
        if len(parts) != 2:
            raise _TemplateError(f"invalid env expression: {expression}")
        try:
            name = ast.literal_eval(parts[1])
        except (SyntaxError, ValueError) as exc:
            raise _TemplateError(f"invalid env expression: {expression}") from exc
        if not isinstance(name, str):
            raise _TemplateError(f"invalid env name: {expression}")
        try:
            return values[name]
        except KeyError as exc:
            raise _MissingTemplateEnvironment(name) from exc
    if expression.startswith(".Env."):
        name = expression[6:]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise _TemplateError(f"unsupported environment lookup: {expression}")
        try:
            return values[name]
        except KeyError as exc:
            raise _MissingTemplateEnvironment(name) from exc
    try:
        literal = ast.literal_eval(expression)
    except (SyntaxError, ValueError) as exc:
        raise _TemplateError(f"unsupported template expression: {expression}") from exc
    if not isinstance(literal, str):
        raise _TemplateError(f"unsupported template literal: {expression}")
    return literal


class _MissingTemplateEnvironment(_TemplateError):
    """Raised when a template references an absent explicit environment value."""


def _condition(expression: str, values: Mapping[str, str]) -> bool:
    parts = expression.split(None, 2)
    if len(parts) != 3 or parts[0] not in {"eq", "ne"}:
        raise _TemplateError(f"unsupported template condition: {expression}")
    left = _lookup(parts[1], values)
    right = _lookup(parts[2], values)
    return left == right if parts[0] == "eq" else left != right


def _find_conditional(
    text: str,
    start: int,
    *,
    limit: int,
) -> tuple[int, int | None, int | None, int]:
    """Return branch spans and the position after a conditional's ``end``."""

    depth = 1
    true_end: int | None = None
    false_start: int | None = None
    position = start
    while True:
        match = _TEMPLATE_TOKEN.search(text, position, limit)
        if match is None:
            raise _TemplateError("unterminated template branch")
        expression = match.group(2).strip()
        if expression.startswith("if "):
            depth += 1
        elif expression == "else" and depth == 1:
            if false_start is not None:
                raise _TemplateError("unexpected template else")
            true_end = match.start()
            false_start = match.end()
        elif expression == "end":
            depth -= 1
            if depth == 0:
                if true_end is None:
                    true_end = match.start()
                false_end = match.start() if false_start is not None else None
                return true_end, false_start, false_end, match.end()
        position = match.end()


def _render_section(
    text: str,
    start: int,
    values: dict[str, str],
    *,
    stop_at_branch: bool = False,
    limit: int | None = None,
) -> tuple[str, int, str | None]:
    """Render until an ``else``/``end`` marker, returning its marker name."""

    output: list[str] = []
    boundary = len(text) if limit is None else limit
    position = start
    while True:
        match = _TEMPLATE_TOKEN.search(text, position, boundary)
        if match is None:
            if stop_at_branch:
                raise _TemplateError("unterminated template branch")
            return "".join(output) + text[position:boundary], boundary, None
        output.append(text[position : match.start()])
        expression = match.group(2).strip()
        position = match.end()
        if expression == "else":
            if not stop_at_branch:
                raise _TemplateError("unexpected template else")
            return "".join(output), position, "else"
        if expression == "end":
            if not stop_at_branch:
                raise _TemplateError("unexpected template end")
            return "".join(output), position, "end"
        if expression.startswith("if "):
            condition = _condition(expression[3:].strip(), values)
            true_end, false_start, false_end, section_end = _find_conditional(
                text,
                position,
                limit=boundary,
            )
            if condition:
                branch_start, branch_end = position, true_end
            elif false_start is None:
                branch_start = branch_end = true_end
            elif false_end is None:
                raise _TemplateError("unterminated template if")
            else:
                branch_start, branch_end = false_start, false_end
            branch_text, branch_position, branch_marker = _render_section(
                text,
                branch_start,
                values,
                limit=branch_end,
            )
            if branch_marker is not None or branch_position != branch_end:
                raise _TemplateError("unterminated template if")
            output.append(branch_text)
            position = section_end
            continue
        if ":=" in expression:
            name, value_expression = (part.strip() for part in expression.split(":=", 1))
            if not re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", name):
                raise _TemplateError(f"unsupported template assignment: {expression}")
            # The caller's mapping is an immutable input contract.  Assignments
            # are evaluated in a private copy by ``render_value``.
            values[name[1:]] = _lookup(value_expression, values)
            continue
        output.append(_lookup(expression, values))


def render_value(
    value: str,
    harness: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Render one explicit profile template for ``harness``.

    Failed/unsupported templates are returned unchanged, while a missing
    explicit environment reference fails loudly so profile compilation cannot
    publish an unresolved secret placeholder.
    """

    if not needs_render(value):
        return value
    values: dict[str, str] = dict(environment or {})
    values["HARNESS"] = harness
    values["h"] = harness
    try:
        rendered, position, marker = _render_section(value, 0, values)
    except _MissingTemplateEnvironment as exc:
        raise ValueError(f"template environment variable {exc.args[0]!r} is missing") from exc
    except _TemplateError:
        return value
    if marker is not None or position != len(value):
        return value
    return rendered


def _json_ready(value: Any, harness: str, environment: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item, harness, environment) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item, harness, environment) for item in value]
    if isinstance(value, str) and needs_render(value):
        return render_value(value, harness, environment=environment)
    return value


def render_mcp_for_harness(
    mcp: Mapping[str, Any],
    harness: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return one JSON-ready harness projection without mutating ``mcp``.

    Immutable profile snapshots use tuples and mapping proxies.  The returned
    structure always uses ordinary dictionaries/lists, recursively preserving
    declaration order while rendering string templates from the explicit
    environment.
    """

    if not isinstance(mcp, Mapping):
        raise TypeError("MCP declaration must be a mapping")
    explicit_environment = dict(environment or {})
    return {
        str(key): _json_ready(value, harness, explicit_environment) for key, value in mcp.items()
    }


def mcp_entry_for_harness(
    mcp: Mapping[str, Any],
    harness: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Render one local or remote MCP entry for JSON-based harnesses."""

    rendered = render_mcp_for_harness(mcp, harness, environment=environment)
    if rendered.get("url") or rendered.get("type") in {"http", "sse"}:
        url = rendered.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError(f"MCP {mcp.get('name', '?')!r} transport is missing 'url'")
        entry: dict[str, Any] = {"type": rendered.get("type") or "http", "url": url}
        if rendered.get("headers") is not None:
            entry["headers"] = rendered["headers"]
        return entry

    command = rendered.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError(f"MCP {mcp.get('name', '?')!r} is missing 'command'")
    entry = {"command": command}
    if rendered.get("args") is not None:
        entry["args"] = rendered["args"]
    if rendered.get("env") is not None:
        entry["env"] = rendered["env"]
    return entry


__all__ = ["mcp_entry_for_harness", "needs_render", "render_mcp_for_harness", "render_value"]
