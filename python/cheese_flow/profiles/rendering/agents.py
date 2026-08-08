"""Shared agent-body, metadata, and capability transformations."""

from __future__ import annotations

from collections.abc import Mapping, MutableSequence, MutableSet, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .assets import claim_destination, track_file

_WRITE_TOOLS = frozenset(
    {
        "Edit",
        "Write",
        "MultiEdit",
        "NotebookEdit",
        "mcp__tilth__tilth_write",
    }
)


_SUPPORTED_HARNESSES = frozenset({"claude", "codex", "copilot", "crush", "cursor", "opencode"})


def _as_entries(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError("agent list settings must be non-string sequences")
    entries = tuple(value)
    if any(not isinstance(entry, str) for entry in entries):
        raise ValueError("agent list settings must contain only strings")
    return entries


def item_harnesses(item: Mapping[str, Any], defaults: Sequence[str]) -> tuple[str, ...]:
    """Return one validated, literal harness selection for a renderable item."""

    if "harnesses" not in item:
        return tuple(defaults)
    harnesses = _as_entries(item["harnesses"])
    unknown = sorted(set(harnesses) - _SUPPORTED_HARNESSES)
    if unknown:
        raise ValueError(f"item harnesses contain unsupported harnesses: {unknown}")
    return harnesses


def _covers(entry: str, tool: str) -> bool:
    """Return whether a literal or trailing-star entry covers a tool."""

    return entry == tool or (entry.endswith("*") and tool.startswith(entry[:-1]))


def _write_tool_available(tool: str, tools: tuple[str, ...], disallowed: tuple[str, ...]) -> bool:
    if any(_covers(entry, tool) for entry in disallowed):
        return False
    return not tools or any(_covers(entry, tool) for entry in tools)


def agent_is_read_only(item: Mapping[str, Any]) -> bool:
    """Return whether no built-in or write-capable MCP tool is reachable.

    A whitelist is exhaustive; an empty/missing whitelist grants all tools.
    A trailing-star entry grants the whole MCP server namespace, so
    ``mcp__tilth__*`` correctly keeps an agent writable.
    """

    tools = _as_entries(item.get("tools"))
    disallowed = _as_entries(item.get("disallowedTools"))
    return not any(_write_tool_available(tool, tools, disallowed) for tool in _WRITE_TOOLS)


def strip_frontmatter(text: str) -> str:
    """Remove one closed YAML frontmatter block at the beginning of ``text``."""

    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            return "".join(lines[index + 1 :])
    return text


def serialize_frontmatter(frontmatter: Mapping[str, Any]) -> str:
    """Serialize YAML frontmatter deterministically and safely."""

    rendered = yaml.safe_dump(
        dict(frontmatter),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    return rendered.rstrip("\n")


def claude_agent_frontmatter(item: Mapping[str, Any]) -> dict[str, str]:
    """Build the deterministic metadata mapping for a shared Claude agent."""

    name = item.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("agent name must be a non-empty string")
    frontmatter: dict[str, str] = {"name": name}
    for field in ("description", "color", "effort"):
        if field not in item or item[field] in (None, ""):
            continue
        if not isinstance(item[field], str):
            raise ValueError(f"agent {field} must be a string")
        frontmatter[field] = item[field]
    tools = _as_entries(item.get("tools"))
    if tools:
        frontmatter["tools"] = ", ".join(tools)
    disallowed = _as_entries(item.get("disallowedTools"))
    if disallowed:
        frontmatter["disallowedTools"] = f"[{', '.join(disallowed)}]"
    models = item.get("models") or {}
    if not isinstance(models, Mapping):
        raise ValueError("agent models must be a mapping")
    model = models.get("claude") or ""
    if model:
        if not isinstance(model, str):
            raise ValueError("agent model must be a string")
        frontmatter["model"] = model
    max_turns = item.get("maxTurns")
    if max_turns is not None:
        frontmatter["maxTurns"] = str(max_turns)
    skills = _as_entries(item.get("skills"))
    if skills:
        frontmatter["skills"] = f"[{', '.join(skills)}]"
    return frontmatter


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"agent output name must be a single relative path component: {name!r}")
    return name


def write_shared_claude_agent(
    target: Path,
    name: str,
    body_path: Path,
    frontmatter: Mapping[str, Any] | None,
    out_files: MutableSequence[str],
    *,
    claims: MutableSet[str] | None = None,
) -> None:
    """Write a shared ``.claude/agents/<name>.md`` from explicit inputs."""

    name = _safe_name(name)
    body_path = Path(body_path)
    if not body_path.is_file():
        raise FileNotFoundError(f"agent body not found: {body_path}")
    relative = f".claude/agents/{name}.md"
    destination = Path(target) / PurePosixPath(relative)
    claim_destination(claims, target, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pieces: list[str] = []
    if frontmatter:
        pieces.extend(("---\n", serialize_frontmatter(frontmatter) + "\n", "---\n"))
    pieces.append(strip_frontmatter(body_path.read_text(encoding="utf-8")))
    destination.write_text("".join(pieces), encoding="utf-8")
    track_file(out_files, relative)


_OVERRIDE_SUBDIRS = {
    "agent": "agents",
    "agents": "agents",
    "agent_singular": "agent",
    "opencode_agent": "agent",
    "command": "commands",
    "commands": "commands",
}


def render_model_override(
    target: Path,
    harness: str,
    kind: str,
    name: str,
    body_path: Path,
    model: str,
    out_files: MutableSequence[str],
    *,
    claims: MutableSet[str] | None = None,
) -> None:
    """Write a per-harness model override, omitting ``inherit``/empty models."""

    if model in {"", "inherit"}:
        return
    subdir = _OVERRIDE_SUBDIRS.get(kind)
    if subdir is None:
        raise ValueError(f"unknown model override kind: {kind!r}")
    name = _safe_name(name)
    body_path = Path(body_path)
    if not body_path.is_file():
        raise FileNotFoundError(f"agent body not found: {body_path}")
    relative = f".{_safe_name(harness)}/{subdir}/{name}.md"
    destination = Path(target) / PurePosixPath(relative)
    claim_destination(claims, target, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = strip_frontmatter(body_path.read_text(encoding="utf-8"))
    metadata = serialize_frontmatter({"model": model})
    destination.write_text(f"---\n{metadata}\n---\n{body}", encoding="utf-8")
    track_file(out_files, relative)


__all__ = [
    "agent_is_read_only",
    "claude_agent_frontmatter",
    "item_harnesses",
    "render_model_override",
    "serialize_frontmatter",
    "strip_frontmatter",
    "write_shared_claude_agent",
]
