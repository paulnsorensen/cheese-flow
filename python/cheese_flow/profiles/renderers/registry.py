"""Closed harness registry for profile rendering and launch dispatch."""

from __future__ import annotations

from importlib import import_module
from typing import Final

from cheese_flow.profiles.renderers.base import Renderer

COMPILE_HARNESSES: Final[frozenset[str]] = frozenset(
    {"claude", "codex", "copilot", "crush", "cursor", "opencode"}
)
LAUNCH_HARNESSES: Final[frozenset[str]] = frozenset(
    {"claude", "codex", "copilot", "crush", "cursor", "opencode"}
)
ISOLATED_LAUNCH_HARNESSES: Final[frozenset[str]] = frozenset({"claude", "codex", "opencode"})

_RENDERER_CLASSES: Final[dict[str, tuple[str, ...]]] = {
    "claude": ("ClaudeRenderer",),
    "codex": ("CodexRenderer",),
    "copilot": ("CopilotRenderer",),
    "crush": ("CrushRenderer",),
    "cursor": ("CursorRenderer",),
    "opencode": ("OpencodeRenderer",),
}


def renderer(harness: str) -> Renderer:
    """Return the renderer for one closed-v1 harness name.

    Concrete renderer modules are imported only when this lookup is used.  A
    renderer lookup therefore keeps this seam importable before the individual
    harness curds have supplied their modules, while still failing closed for
    names outside the compile/launch registry.
    """

    if harness not in LAUNCH_HARNESSES:
        raise ValueError(f"unsupported harness: {harness}")

    module = import_module(f"{__package__}.{harness}")
    for class_name in _RENDERER_CLASSES[harness]:
        renderer_class = getattr(module, class_name, None)
        if renderer_class is not None:
            instance = renderer_class()
            if not isinstance(instance, Renderer):
                raise TypeError(f"renderer {harness!r} does not implement Renderer")
            if instance.name != harness:
                raise ValueError(f"renderer {harness!r} has name {instance.name!r}")
            return instance

    expected = ", ".join(_RENDERER_CLASSES[harness])
    raise TypeError(f"renderer module {module.__name__!r} exports none of: {expected}")


__all__ = [
    "COMPILE_HARNESSES",
    "ISOLATED_LAUNCH_HARNESSES",
    "LAUNCH_HARNESSES",
    "renderer",
]
