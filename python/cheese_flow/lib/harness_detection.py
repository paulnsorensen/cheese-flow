"""Port of `src/lib/harness-detection.ts` — environment detection for harnesses.

Mirrors the TS surface: `find_command_on_path`, `has_directory`,
`detect_available_harnesses`, `get_harness_install_capability`. Async signatures
match the TS module so `Promise.all` translates to `asyncio.gather` per
decision 6 (no async redesign).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from cheese_flow.adapters import HARNESS_ADAPTERS, HARNESS_NAMES
from cheese_flow.lib.harness import HarnessName

HarnessInstallCapability = Literal["auto-install", "manual-capable", "unsupported"]
HarnessDetectionState = Literal["detected", "not-detected", "bypassed"]
HarnessDetectionKind = Literal["cli", "surface"]


class _HarnessDetectionRequired(TypedDict):
    state: HarnessDetectionState
    reason: str


class HarnessDetection(_HarnessDetectionRequired, total=False):
    kind: HarnessDetectionKind
    value: str


@dataclass(frozen=True)
class HarnessDetectionEnvironment:
    """Override hooks for filesystem/PATH probes (used by tests)."""

    findCommand: Callable[[str], Awaitable[str | None]] | None = None
    hasDirectory: Callable[[str], Awaitable[bool]] | None = None


@dataclass(frozen=True)
class _CliProbe:
    command: str
    kind: Literal["cli"] = "cli"


@dataclass(frozen=True)
class _SurfaceProbe:
    relativePath: str
    kind: Literal["surface"] = "surface"


_HarnessDetectionProbe = _CliProbe | _SurfaceProbe


@dataclass(frozen=True)
class _HarnessInstallProfile:
    capability: HarnessInstallCapability
    probes: tuple[_HarnessDetectionProbe, ...]


_HARNESS_INSTALL_PROFILES: dict[HarnessName, _HarnessInstallProfile] = {
    "claude-code": _HarnessInstallProfile(
        capability="manual-capable",
        probes=(_CliProbe(command="claude"),),
    ),
    "codex": _HarnessInstallProfile(
        capability="manual-capable",
        probes=(_CliProbe(command="codex"),),
    ),
    "cursor": _HarnessInstallProfile(
        capability="auto-install",
        probes=(_SurfaceProbe(relativePath=".cursor"),),
    ),
    "copilot-cli": _HarnessInstallProfile(
        capability="auto-install",
        probes=(_CliProbe(command="copilot"),),
    ),
}


def get_harness_install_capability(harness: HarnessName) -> HarnessInstallCapability:
    return _HARNESS_INSTALL_PROFILES[harness].capability


async def find_command_on_path(
    command: str,
    search_path: str | None = None,
) -> str | None:
    """Locate an executable on PATH. Returns the absolute path or `None`."""

    if search_path is not None:
        resolved_search_path = search_path
    else:
        resolved_search_path = os.environ.get("PATH") or os.environ.get("Path") or ""  # noqa: SIM112
    directories = [d for d in resolved_search_path.split(os.pathsep) if d]
    extensions = _path_extensions() if sys.platform == "win32" else [""]

    for directory in directories:
        for extension in extensions:
            candidate = Path(directory) / _with_extension(command, extension)
            if await asyncio.to_thread(_is_executable, candidate):
                return str(candidate)

    return None


async def has_directory(directory_path: str) -> bool:
    return await asyncio.to_thread(Path(directory_path).is_dir)


async def detect_available_harnesses(
    *,
    project_root: str,
    environment: HarnessDetectionEnvironment | None = None,
) -> dict[HarnessName, HarnessDetection]:
    find_command = (
        environment.findCommand
        if environment is not None and environment.findCommand is not None
        else find_command_on_path
    )
    check_directory = (
        environment.hasDirectory
        if environment is not None and environment.hasDirectory is not None
        else has_directory
    )

    detections = await asyncio.gather(
        *[
            _detect_harness(
                harness=harness,
                project_root=project_root,
                find_command=find_command,
                has_directory=check_directory,
            )
            for harness in HARNESS_NAMES
        ]
    )

    return dict(zip(HARNESS_NAMES, detections, strict=True))


async def _detect_harness(
    *,
    harness: HarnessName,
    project_root: str,
    find_command: Callable[[str], Awaitable[str | None]],
    has_directory: Callable[[str], Awaitable[bool]],
) -> HarnessDetection:
    display_name = HARNESS_ADAPTERS[harness].displayName
    profile = _HARNESS_INSTALL_PROFILES[harness]

    for probe in profile.probes:
        if isinstance(probe, _CliProbe):
            command_path = await find_command(probe.command)
            if command_path is not None:
                return {
                    "state": "detected",
                    "kind": "cli",
                    "value": command_path,
                    "reason": f'Auto-detected {display_name} via CLI "{probe.command}".',
                }
            continue

        directory_path = str(Path(project_root) / probe.relativePath)
        if await has_directory(directory_path):
            return {
                "state": "detected",
                "kind": "surface",
                "value": directory_path,
                "reason": f"Auto-detected {display_name} via {probe.relativePath}/.",
            }

    return {
        "state": "not-detected",
        "reason": f"No {display_name} {_describe_probes(profile.probes)} detected.",
    }


def _describe_probes(probes: tuple[_HarnessDetectionProbe, ...]) -> str:
    return " or ".join(_describe_probe(probe) for probe in probes)


def _describe_probe(probe: _HarnessDetectionProbe) -> str:
    if isinstance(probe, _CliProbe):
        return f'CLI "{probe.command}" on PATH'
    return f'project surface "{probe.relativePath}"'


def _is_executable(candidate: Path) -> bool:
    try:
        return candidate.is_file() and os.access(candidate, os.X_OK)
    except OSError:
        return False


def _path_extensions() -> list[str]:
    configured = os.environ.get("PATHEXT", ".EXE;.CMD;.BAT;.COM")
    return [ext for ext in configured.split(";") if ext]


def _with_extension(command: str, extension: str) -> str:
    if extension and command.lower().endswith(extension.lower()):
        return command
    return f"{command}{extension}"


__all__ = [
    "HarnessDetection",
    "HarnessDetectionEnvironment",
    "HarnessDetectionKind",
    "HarnessDetectionState",
    "HarnessInstallCapability",
    "detect_available_harnesses",
    "find_command_on_path",
    "get_harness_install_capability",
    "has_directory",
]
