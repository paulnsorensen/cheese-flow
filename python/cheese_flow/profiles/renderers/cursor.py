"""Cursor profile rendering.

The renderer only reads the resolved profile and the caller-supplied source and
output roots.  In particular, Cursor is a non-isolated harness: launch
projection never inspects or changes user configuration.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping, MutableSet, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..models import LaunchSpec
from ..rendering.agents import (
    claude_agent_frontmatter,
    item_harnesses,
    render_model_override,
    serialize_frontmatter,
    write_shared_claude_agent,
)
from ..rendering.assets import body_abs, claim_destination, copy_hook_shared_assets, track_file
from ..rendering.template import mcp_entry_for_harness

_CURSOR = "cursor"
_DEFAULT_AGENTS = ("claude", "codex", "opencode", "cursor", "copilot")
_DEFAULT_COMMANDS = _DEFAULT_AGENTS
_DEFAULT_SKILLS = _DEFAULT_AGENTS
_DEFAULT_MCPS = ("claude", "codex", "opencode", "cursor")
_DEFAULT_HOOKS = ("claude",)


class CursorRenderer:
    """Render profile-owned Cursor artifacts under an explicit target root."""

    name = _CURSOR

    def render(
        self,
        profile: Any,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        """Render Cursor files and return generated paths in write order."""
        del logical_root
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        generated: list[str] = []
        claims: set[str] = set()

        self._render_mcp(profile, target, generated, claims)
        self._render_agents(profile, target, generated, claims)
        self._render_skills(profile, target, generated, claims)
        self._render_commands(profile, target, generated, claims)
        self._render_hooks(profile, target, generated, claims)
        self._warn_unsupported_permissions(profile)

        return tuple(PurePosixPath(path) for path in generated)

    def launch_spec(
        self,
        profile: Any,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        """Return Cursor's direct executable projection.

        ``overlay`` and ``profile`` are accepted for the common renderer
        protocol.  Cursor has no runtime isolation mechanism, so neither may
        alter this explicit non-isolated projection.
        """
        del profile, overlay
        return LaunchSpec(
            executable=_CURSOR,
            argv=(_CURSOR, *arguments),
            environment=dict(environment),
        )

    @staticmethod
    def _render_agents(
        profile: Any,
        target: Path,
        generated: list[str],
        claims: MutableSet[str],
    ) -> None:
        for item in _items(profile, "agents"):
            if not _selected(item, _DEFAULT_AGENTS):
                continue
            name = _component(item.get("name"), label="agent name")
            body = body_abs(item)
            if body is None:
                continue
            frontmatter = claude_agent_frontmatter(item)
            write_shared_claude_agent(
                target,
                name,
                body,
                frontmatter,
                generated,
                claims=claims,
            )
            model = _model_for(item)
            if model and model != "inherit":
                render_model_override(
                    target,
                    _CURSOR,
                    "agent",
                    name,
                    body,
                    model,
                    generated,
                    claims=claims,
                )

    @staticmethod
    def _render_skills(
        profile: Any,
        target: Path,
        generated: list[str],
        claims: MutableSet[str],
    ) -> None:
        for item in _items(profile, "skills"):
            if not _selected(item, _DEFAULT_SKILLS):
                continue
            name = _component(item.get("name"), label="skill name")
            source_rel = _relative_path(item.get("path"), label="skill path")
            source_root = _source_root(item)
            source = source_root.joinpath(*source_rel.parts)
            if not source.is_dir():
                raise NotADirectoryError(f"profile skill source is not a directory: {source}")
            relative = PurePosixPath(".agents", "skills", name)
            destination = target / relative
            claim_destination(claims, target, destination)
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                if not destination.is_dir():
                    destination.unlink()
                else:
                    shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            track_file(generated, relative.as_posix())

    @staticmethod
    def _render_commands(
        profile: Any,
        target: Path,
        generated: list[str],
        claims: MutableSet[str],
    ) -> None:
        for item in _items(profile, "commands"):
            if not _selected(item, _DEFAULT_COMMANDS):
                continue
            name = _component(item.get("name"), label="command name")
            body = body_abs(item)
            if body is None:
                continue
            model = _model_for(item)
            description = str(item.get("description") or "")
            metadata: dict[str, str] = {}
            if description:
                metadata["description"] = description
            if model:
                metadata["model"] = model
            content = ""
            if metadata:
                content = f"---\n{serialize_frontmatter(metadata)}\n---\n"
            content += body.read_text(encoding="utf-8")
            relative = PurePosixPath(".cursor", "commands", f"{name}.md")
            destination = target / relative
            claim_destination(claims, target, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            track_file(generated, relative.as_posix())

    @staticmethod
    def _render_hooks(
        profile: Any,
        target: Path,
        generated: list[str],
        claims: MutableSet[str],
    ) -> None:
        hooks: list[dict[str, str]] = []
        for item in _items(profile, "hooks"):
            if not _selected(item, _DEFAULT_HOOKS):
                continue
            script_rel = _relative_path(item.get("script"), label="hook script")
            source = _source_root(item).joinpath(*script_rel.parts)
            if not source.is_file():
                raise FileNotFoundError(f"profile hook script not found: {source}")
            script_name = script_rel.name
            destination = target / ".cursor" / "hooks" / script_name
            claim_destination(claims, target, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o755)
            track_file(generated, PurePosixPath(".cursor", "hooks", script_name).as_posix())
            copy_hook_shared_assets(
                item,
                target / ".cursor" / "hooks",
                target,
                generated,
                claims=claims,
            )
            hooks.append(
                {
                    "event": str(item.get("event") or ""),
                    "matcher": str(item.get("matcher") or ""),
                    "command": PurePosixPath(".cursor", "hooks", script_name).as_posix(),
                }
            )

        if not hooks:
            return
        relative = PurePosixPath(".cursor", "hooks.json")
        destination = target / relative
        claim_destination(claims, target, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
        track_file(generated, relative.as_posix())

    @staticmethod
    def _render_mcp(
        profile: Any,
        target: Path,
        generated: list[str],
        claims: MutableSet[str],
    ) -> None:
        if not bool(getattr(profile, "isolated", False)):
            return
        selected = [item for item in _items(profile, "mcps") if _selected(item, _DEFAULT_MCPS)]
        if not selected:
            return

        relative = PurePosixPath(".cursor", "mcp.json")
        destination = target / relative
        existing: dict[str, Any] = {}
        if destination.is_file():
            parsed = json.loads(destination.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError(f"Cursor MCP config must be a JSON object: {destination}")
            existing = parsed
        servers = existing.get("mcpServers")
        servers = {} if not isinstance(servers, dict) else dict(servers)
        for item in selected:
            name = _component(item.get("name"), label="MCP name")
            entry = mcp_entry_for_harness(
                item,
                _CURSOR,
                environment=profile.template_environment or profile.env,
            )
            if "command" in entry:
                entry.setdefault("args", [])
                entry.setdefault("env", {})
            servers[name] = entry
        existing["mcpServers"] = servers
        claim_destination(claims, target, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        track_file(generated, relative.as_posix())

    @staticmethod
    def _warn_unsupported_permissions(profile: Any) -> None:
        allow = tuple(getattr(profile, "permissions_allow", ()) or ())
        deny = tuple(getattr(profile, "permissions_deny", ()) or ())
        if allow or deny:
            print(
                "cursor: permissions are UI-only; no permission file was generated",
                file=sys.stderr,
            )


def _items(profile: Any, field: str) -> Sequence[Mapping[str, Any]]:
    value = getattr(profile, field, ()) or ()
    return tuple(value)


def _selected(item: Mapping[str, Any], default: tuple[str, ...]) -> bool:
    return _CURSOR in item_harnesses(item, default)


def _component(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty name")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{label} must not contain path separators: {value!r}")
    return value


def _relative_path(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal: {value!r}")
    return path


def _source_root(item: Mapping[str, Any]) -> Path:
    source = item.get("_source_dir")
    if source is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(source)


def _model_for(item: Mapping[str, Any]) -> str | None:
    models = item.get("models")
    if not isinstance(models, Mapping):
        return None
    model = models.get(_CURSOR)
    return model if isinstance(model, str) and model else None


__all__ = ["CursorRenderer"]
