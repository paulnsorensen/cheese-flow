"""Verbatim port of `tests/frontmatter.test.ts`."""

from __future__ import annotations

import pytest
from cheese_flow.lib.frontmatter import parse_frontmatter


def test_parses_valid_frontmatter_and_body() -> None:
    content = "---\nname: cheddar\nage: 12\n---\nbody text\n"
    data, body = parse_frontmatter(content)
    assert data == {"name": "cheddar", "age": 12}
    assert body == "body text\n"


def test_handles_windows_crlf_line_endings() -> None:
    content = "---\r\nname: gouda\r\n---\r\nbody\r\n"
    data, body = parse_frontmatter(content)
    assert data == {"name": "gouda"}
    assert body == "body\r\n"


def test_returns_an_empty_object_when_frontmatter_is_empty() -> None:
    content = "---\n\n---\nbody only\n"
    data, body = parse_frontmatter(content)
    assert data == {}
    assert body == "body only\n"


def test_throws_when_frontmatter_delimiters_are_missing() -> None:
    with pytest.raises(ValueError, match="Expected YAML frontmatter"):
        parse_frontmatter("no markers here")


def test_throws_when_yaml_inside_frontmatter_is_invalid() -> None:
    with pytest.raises(ValueError):
        parse_frontmatter("---\nname: : broken\n---\nbody\n")
