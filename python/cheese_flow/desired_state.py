"""TOML validation and atomic persistence of the cheese-flow manifest."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.models import DesiredState


def default_config_path() -> Path:
    """Return ``$XDG_CONFIG_HOME/cheese/config.toml`` (``~/.config`` fallback)."""
    raise NotImplementedError


def load_desired_state(path: Path) -> DesiredState:
    """Parse and validate the manifest at ``path``.

    Unknown keys or names, relative paths, duplicates, missing required
    components, and selections outside the search roots are validation errors.
    """
    raise NotImplementedError


def save_desired_state(state: DesiredState, path: Path) -> None:
    """Write ``state`` to ``path`` atomically, replacing any existing manifest."""
    raise NotImplementedError
