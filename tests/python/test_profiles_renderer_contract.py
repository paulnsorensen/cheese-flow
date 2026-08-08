"""Behavioral tests for the profile renderer seam and closed registries."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.renderers.base import Renderer
from cheese_flow.profiles.renderers.registry import (
    COMPILE_HARNESSES,
    ISOLATED_LAUNCH_HARNESSES,
    LAUNCH_HARNESSES,
    renderer,
)

_EXPECTED_RENDER_HARNESSES = frozenset(
    {"claude", "codex", "copilot", "crush", "cursor", "opencode"}
)
_EXPECTED_ISOLATED_HARNESSES = frozenset({"claude", "codex", "opencode"})


class _StructuralRenderer:
    """Small fake proving the protocol is structural and root-explicit."""

    name = "fake"

    def render(
        self,
        profile: object,
        target: Path,
        *,
        logical_root: Path,
    ) -> tuple[PurePosixPath, ...]:
        assert profile is not None
        assert target.is_absolute()
        assert logical_root.is_absolute()
        return (PurePosixPath(".claude/settings.json"),)

    def launch_spec(
        self,
        profile: object,
        overlay: Path | None,
        arguments: tuple[str, ...],
        environment: Mapping[str, str],
    ) -> LaunchSpec:
        assert profile is not None
        assert overlay is None or overlay.is_absolute()
        return LaunchSpec(
            executable=self.name,
            argv=(self.name, *arguments),
            environment=environment,
        )


def test_renderer_protocol_is_structural_and_roots_are_explicit(tmp_path: Path) -> None:
    fake = _StructuralRenderer()
    assert isinstance(fake, Renderer)

    target = tmp_path / "work"
    logical_root = tmp_path / "logical"
    assert fake.render(object(), target, logical_root=logical_root) == (
        PurePosixPath(".claude/settings.json"),
    )
    assert fake.launch_spec(object(), None, ("--version",), {"HOME": "/tmp"}).argv == (
        "fake",
        "--version",
    )


def test_renderer_render_requires_a_keyword_only_logical_root() -> None:
    parameters = inspect.signature(Renderer.render).parameters
    logical_root = parameters["logical_root"]
    assert logical_root.kind is inspect.Parameter.KEYWORD_ONLY
    assert logical_root.default is inspect.Parameter.empty


def test_renderer_launch_spec_has_the_frozen_boundary() -> None:
    parameters = tuple(inspect.signature(Renderer.launch_spec).parameters)
    assert parameters == ("self", "profile", "overlay", "arguments", "environment")


def test_renderer_registries_are_closed() -> None:
    assert COMPILE_HARNESSES == _EXPECTED_RENDER_HARNESSES
    assert LAUNCH_HARNESSES == _EXPECTED_RENDER_HARNESSES
    assert ISOLATED_LAUNCH_HARNESSES == _EXPECTED_ISOLATED_HARNESSES
    assert all(
        isinstance(names, frozenset)
        for names in (
            COMPILE_HARNESSES,
            LAUNCH_HARNESSES,
            ISOLATED_LAUNCH_HARNESSES,
        )
    )


@pytest.mark.parametrize("harness", ["", "pi", "claude ", "opencode-global"])
def test_renderer_rejects_harnesses_outside_the_closed_registry(harness: str) -> None:
    with pytest.raises(ValueError, match="unsupported harness"):
        renderer(harness)
