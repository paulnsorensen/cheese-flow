"""Deterministic Crush profile rendering from explicit inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableSequence
from pathlib import Path, PurePosixPath
from typing import Any

from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.rendering.agents import item_harnesses
from cheese_flow.profiles.rendering.assets import (
    claim_destination,
    copy_hook_shared_assets,
    track_file,
)
from cheese_flow.profiles.rendering.template import render_mcp_for_harness
from cheese_flow.profiles.source import ResolvedProfile

_CRUSH_MCP_DEFAULT = ("claude", "codex", "opencode", "cursor", "crush")
_CRUSH_HOOK_DEFAULT = ("claude",)
_CRUSH_CONFIG_REL = PurePosixPath(".config", "crush", "crush.json")
_CRUSH_HOOKS_DIR_REL = PurePosixPath(".config", "crush", "hooks")


class CrushRenderer:
    """Render Crush's profile-owned configuration below an explicit target root."""

    name = "crush"
    mcp_default = _CRUSH_MCP_DEFAULT

    def render(
        self,
        profile: ResolvedProfile,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        """Render Crush MCP and ``PreToolUse`` hook surfaces.

        Crush has no profile-owned agent, skill, or command trees.  Its merged
        configuration is only managed for isolated profiles; the caller owns
        the target tree and all source paths are carried by the resolved
        profile items.
        """
        if not profile.isolated:
            return ()

        target = Path(target)
        logical_root = Path(logical_root)
        config_path = target / _CRUSH_CONFIG_REL
        data: dict[str, Any] = {}
        generated: list[str] = []
        claims: dict[str, tuple[bytes, int]] = {}

        changed = self._merge_mcps(profile, data)
        changed = (
            self._merge_hooks(profile, target, logical_root, data, generated, claims) or changed
        )
        if changed:
            payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            if claim_destination(
                claims,
                target,
                config_path,
                content=payload.encode(),
                mode=0o644,
            ):
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(payload, encoding="utf-8")
        return tuple(PurePosixPath(path) for path in generated)

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        """Return Crush's direct executable projection."""
        del profile, overlay
        return LaunchSpec(
            executable=self.name,
            argv=(self.name, *arguments),
            environment=dict(environment),
        )

    def _merge_mcps(self, profile: ResolvedProfile, data: dict[str, Any]) -> bool:
        mcps = _items_for(profile.mcps, self.name, _CRUSH_MCP_DEFAULT)
        if not mcps:
            return False

        section = data.get("mcp")
        if not isinstance(section, dict):
            section = {}
            data["mcp"] = section
        for mcp in mcps:
            name = _component(mcp.get("name"), label="MCP name")
            section[name] = _crush_mcp_entry(
                mcp,
                environment=profile.template_environment or profile.env,
            )
        return True

    def _merge_hooks(
        self,
        profile: ResolvedProfile,
        target: Path,
        logical_root: Path,
        data: dict[str, Any],
        generated: MutableSequence[str],
        claims: dict[str, tuple[bytes, int]],
    ) -> bool:
        hooks = _items_for(profile.hooks, self.name, _CRUSH_HOOK_DEFAULT)
        if not hooks:
            return False

        section = data.get("hooks")
        section = section if isinstance(section, dict) else {}
        existing = section.get("PreToolUse")
        entries: list[Any] = list(existing) if isinstance(existing, list) else []
        hooks_dir = target / _CRUSH_HOOKS_DIR_REL
        changed = False

        for hook in hooks:
            if hook.get("event") != "PreToolUse":
                continue
            script = _relative_path(hook.get("script"), label="Crush hook script")
            source_dir = _source_dir(hook)
            source = source_dir.joinpath(*script.parts)
            if not source.is_file():
                raise FileNotFoundError(f"Crush hook script not found: {source}")

            basename = script.name
            destination = hooks_dir / basename
            content = source.read_bytes()
            if claim_destination(
                claims,
                target,
                destination,
                content=content,
                mode=0o755,
            ):
                hooks_dir.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o755)
            track_file(generated, (_CRUSH_HOOKS_DIR_REL / basename).as_posix())
            copy_hook_shared_assets(
                hook,
                target / PurePosixPath(".config", "crush"),
                target,
                generated,
                claims=claims,
            )

            entry: dict[str, Any] = {
                "command": str(logical_root / _CRUSH_HOOKS_DIR_REL / basename),
            }
            matcher = hook.get("matcher")
            if matcher not in (None, ""):
                entry["matcher"] = matcher
            timeout = hook.get("timeout")
            if timeout not in (None, ""):
                entry["timeout"] = int(timeout)

            entries = [
                existing_entry
                for existing_entry in entries
                if not (
                    isinstance(existing_entry, Mapping)
                    and existing_entry.get("command") == entry["command"]
                )
            ]
            entries.append(entry)
            changed = True

        if not changed:
            return False
        section["PreToolUse"] = entries
        data["hooks"] = section
        return True


def _items_for(
    items: tuple[Mapping[str, Any], ...],
    harness: str,
    default: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in items if harness in item_harnesses(item, default))


def _component(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty name")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise ValueError(f"{label} must be a single relative path component")
    return value


def _relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal")
    return path


def _source_dir(item: Mapping[str, Any]) -> Path:
    source = item.get("_source_dir")
    if source is None:
        raise ValueError("profile item requires an explicit source root")
    return Path(source)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"unsupported Crush MCP value type: {type(value).__name__}")


def _crush_mcp_entry(mcp: Mapping[str, Any], *, environment: Mapping[str, str]) -> dict[str, Any]:
    candidate = dict(mcp)
    args = candidate.get("args")
    if isinstance(args, (list, tuple)):
        candidate["args"] = list(args)
    env = candidate.get("env")
    if isinstance(env, Mapping):
        candidate["env"] = dict(env)
    headers = candidate.get("headers")
    if isinstance(headers, Mapping):
        candidate["headers"] = dict(headers)
    rendered = render_mcp_for_harness(candidate, "crush", environment=environment)

    if rendered.get("url") or rendered.get("type") in {"http", "sse"}:
        url = rendered.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError(f"MCP {mcp.get('name', '?')!r} transport is missing 'url'")
        entry: dict[str, Any] = {
            "type": str(rendered.get("type") or "http"),
            "url": url,
        }
        headers = rendered.get("headers")
        if headers is not None:
            if not isinstance(headers, Mapping):
                raise ValueError(f"MCP {mcp.get('name', '?')!r} headers must be a mapping")
            entry["headers"] = _json_value(headers)
    else:
        command = rendered.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError(f"MCP {mcp.get('name', '?')!r} is missing 'command'")
        entry = {
            "type": str(rendered.get("type") or "stdio"),
            "command": command,
        }
        for key in ("args", "env"):
            value = rendered.get(key)
            if value is not None:
                entry[key] = _json_value(value)

    disabled_tools = rendered.get("disabled_tools")
    if isinstance(disabled_tools, (list, tuple)) and disabled_tools:
        entry["disabled_tools"] = _json_value(disabled_tools)
    timeout = rendered.get("timeout")
    if timeout not in (None, ""):
        entry["timeout"] = int(timeout)
    disabled = rendered.get("disabled")
    if isinstance(disabled, bool):
        entry["disabled"] = disabled
    return entry


__all__ = ["CrushRenderer"]
