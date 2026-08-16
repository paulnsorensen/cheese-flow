"""Native install commands and positive postconditions, one adapter per component."""

from __future__ import annotations

from cheese_flow.adapters.easy_cheese import EasyCheeseAdapter
from cheese_flow.adapters.hallouminate import HallouminateAdapter
from cheese_flow.adapters.milknado import MilknadoAdapter
from cheese_flow.adapters.tilth import TilthAdapter
from cheese_flow.models import CommandRunner, ComponentAdapters

__all__ = [
    "EasyCheeseAdapter",
    "HallouminateAdapter",
    "MilknadoAdapter",
    "TilthAdapter",
    "default_component_adapters",
]


def default_component_adapters(runner: CommandRunner) -> ComponentAdapters:
    """Build the adapter for every supported component, keyed by component name."""
    adapters = (
        HallouminateAdapter(runner),
        EasyCheeseAdapter(runner),
        TilthAdapter(runner),
        MilknadoAdapter(runner),
    )
    return {adapter.name: adapter for adapter in adapters}
