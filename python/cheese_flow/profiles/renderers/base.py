"""Shared protocol for resolved-profile harness renderers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cheese_flow.profiles.models import LaunchSpec

if TYPE_CHECKING:
    from cheese_flow.profiles.source import ResolvedProfile


@runtime_checkable
class Renderer(Protocol):
    """The boundary implemented by every profile harness renderer.

    Renderers consume only an already-resolved profile and caller-owned roots.
    ``target`` is the physical work root; ``logical_root`` is the explicit
    resolved deployment root used when generated content embeds a root path.
    """

    name: str

    def render(
        self,
        profile: ResolvedProfile,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        """Render deterministic relative artefact paths beneath ``target``."""
        ...

    def launch_spec(
        self,
        profile: ResolvedProfile,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        """Build a launch specification without discovering roots or state."""
        ...


__all__ = ["Renderer"]
