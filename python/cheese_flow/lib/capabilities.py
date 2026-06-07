"""Port of `src/lib/capabilities.ts` — adapter capability inversion helpers."""

from __future__ import annotations

from typing import Literal

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.harness import HarnessName

CapabilityKind = Literal["skill", "agent"]


def field_support(kind: CapabilityKind) -> dict[str, list[HarnessName]]:
    result: dict[str, list[HarnessName]] = {}
    for name, adapter in HARNESS_ADAPTERS.items():
        keys = (
            adapter.capabilities.skillFrontmatterKeys
            if kind == "skill"
            else adapter.capabilities.agentFrontmatterKeys
        )
        for key in keys:
            result.setdefault(key, []).append(name)
    return result


def event_support() -> dict[str, list[HarnessName]]:
    result: dict[str, list[HarnessName]] = {}
    for name, adapter in HARNESS_ADAPTERS.items():
        for event in adapter.capabilities.hookEvents:
            result.setdefault(event, []).append(name)
    return result


def tool_support() -> dict[str, list[HarnessName]]:
    result: dict[str, list[HarnessName]] = {}
    for name, adapter in HARNESS_ADAPTERS.items():
        for tool in adapter.capabilities.toolNames:
            result.setdefault(tool, []).append(name)
    return result
