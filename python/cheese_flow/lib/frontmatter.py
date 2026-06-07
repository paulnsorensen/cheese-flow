"""Port of `src/lib/frontmatter.ts` — split YAML frontmatter from a markdown body."""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_FRONTMATTER_PATTERN = re.compile(
    r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$",
    re.DOTALL,
)


def _make_yaml_loader() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    return yaml


_YAML = _make_yaml_loader()


def parse_frontmatter(content: str) -> tuple[Any, str]:
    """Return ``(data, body)`` parsed from a ``---``-delimited markdown source.

    Mirrors the TS helper: raises when the delimiters are absent or YAML is
    malformed; returns an empty dict when the frontmatter region is empty.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if match is None:
        raise ValueError("Expected YAML frontmatter bounded by --- markers.")

    raw_frontmatter = match.group(1)
    body = match.group(2)

    # Append a trailing newline so ruamel.yaml retains the clip-chomp newline on
    # ``>`` / ``|`` block scalars; the Node ``yaml`` parser keeps that newline
    # implicitly and downstream emitters depend on it (e.g. cursor rule pages).
    try:
        loaded = _YAML.load(StringIO(raw_frontmatter + "\n"))
    except YAMLError as error:
        raise ValueError(str(error)) from error

    return (loaded if loaded is not None else {}, body)
