"""Port of `src/lib/install-plan.ts` — harness install plan construction.

Builds a typed plan describing which harnesses to install (auto-detect vs.
explicit `--harness` overrides), with per-harness selection status and reason.
The TS module re-exports a slice of `harness_detection` for installer
consumers; this module mirrors that surface so US-008's installer port has the
same imports it expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from cheese_flow.adapters import HARNESS_ADAPTERS, HARNESS_NAMES
from cheese_flow.lib.harness import HarnessName
from cheese_flow.lib.harness_detection import (
    HarnessDetection,
    HarnessDetectionEnvironment,
    HarnessDetectionKind,
    HarnessDetectionState,
    HarnessInstallCapability,
    detect_available_harnesses,
    find_command_on_path,
    get_harness_install_capability,
    has_directory,
)

HarnessSelectionMode = Literal["auto-detect", "explicit"]
HarnessSelectionStatus = Literal["selected", "skipped"]


class HarnessInstallPlanEntry(TypedDict):
    harness: HarnessName
    displayName: str
    outputRoot: str
    selection: HarnessSelectionStatus
    capability: HarnessInstallCapability
    detection: HarnessDetection
    reason: str


class _HarnessInstallPlanRequired(TypedDict):
    selectionMode: HarnessSelectionMode
    requestedHarnesses: list[HarnessName]
    selectedHarnesses: list[HarnessName]
    entries: list[HarnessInstallPlanEntry]
    ok: bool


class HarnessInstallPlan(_HarnessInstallPlanRequired, total=False):
    guidance: str


@dataclass(frozen=True)
class _BuildPlanEntryOptions:
    harness: HarnessName
    selection: HarnessSelectionStatus
    detection: HarnessDetection


def parse_harness_name(value: str) -> HarnessName:
    trimmed = value.strip()
    if trimmed in HARNESS_NAMES:
        return trimmed  # type: ignore[return-value]

    raise ValueError(
        f'Unsupported harness "{trimmed}". Expected one of: {", ".join(HARNESS_NAMES)}.'
    )


def dedupe_harness_names(harnesses: list[HarnessName]) -> list[HarnessName]:
    seen: set[HarnessName] = set()
    result: list[HarnessName] = []
    for harness in harnesses:
        if harness in seen:
            continue
        seen.add(harness)
        result.append(harness)
    return result


def parse_harness_overrides(values: list[str]) -> list[HarnessName]:
    flattened: list[HarnessName] = []
    for value in values:
        for piece in value.split(","):
            flattened.append(parse_harness_name(piece))
    return dedupe_harness_names(flattened)


async def create_harness_install_plan(
    *,
    project_root: str,
    environment: HarnessDetectionEnvironment | None = None,
    requested_harnesses: list[HarnessName] | None = None,
) -> HarnessInstallPlan:
    requested = dedupe_harness_names(list(requested_harnesses or []))
    if len(requested) > 0:
        return _build_explicit_install_plan(requested)

    detections = await detect_available_harnesses(
        project_root=project_root, environment=environment
    )
    return _build_auto_detect_install_plan(detections, requested)


def _build_explicit_install_plan(
    requested_harnesses: list[HarnessName],
) -> HarnessInstallPlan:
    requested_set = set(requested_harnesses)
    return {
        "selectionMode": "explicit",
        "requestedHarnesses": requested_harnesses,
        "selectedHarnesses": list(requested_harnesses),
        "ok": True,
        "entries": [
            _build_plan_entry(
                _BuildPlanEntryOptions(
                    harness=harness,
                    selection="selected" if harness in requested_set else "skipped",
                    detection={
                        "state": "bypassed",
                        "reason": "Skipped auto-detect because --harness was provided.",
                    },
                )
            )
            for harness in HARNESS_NAMES
        ],
    }


def _build_auto_detect_install_plan(
    detections: dict[HarnessName, HarnessDetection],
    requested_harnesses: list[HarnessName],
) -> HarnessInstallPlan:
    selected_harnesses: list[HarnessName] = [
        harness for harness in HARNESS_NAMES if detections[harness]["state"] == "detected"
    ]
    entries: list[HarnessInstallPlanEntry] = [
        _build_plan_entry(
            _BuildPlanEntryOptions(
                harness=harness,
                selection="selected" if detections[harness]["state"] == "detected" else "skipped",
                detection=detections[harness],
            )
        )
        for harness in HARNESS_NAMES
    ]
    plan: HarnessInstallPlan = {
        "selectionMode": "auto-detect",
        "requestedHarnesses": requested_harnesses,
        "selectedHarnesses": selected_harnesses,
        "ok": len(selected_harnesses) > 0,
        "entries": entries,
    }
    if len(selected_harnesses) == 0:
        plan["guidance"] = (
            'No installed harnesses detected. Re-run with --harness <name> or use "cheese compile".'
        )
    return plan


def _build_plan_entry(options: _BuildPlanEntryOptions) -> HarnessInstallPlanEntry:
    adapter = HARNESS_ADAPTERS[options.harness]
    selected_reason = (
        "Selected explicitly via --harness."
        if options.detection["state"] == "bypassed"
        else options.detection["reason"]
    )

    if options.selection == "selected":
        reason = selected_reason
    elif options.detection["state"] == "bypassed":
        reason = "Skipped because it was not requested via --harness."
    else:
        reason = options.detection["reason"]

    return {
        "harness": options.harness,
        "displayName": adapter.displayName,
        "outputRoot": adapter.outputRoot,
        "selection": options.selection,
        "capability": get_harness_install_capability(options.harness),
        "detection": options.detection,
        "reason": reason,
    }


__all__ = [
    "HarnessDetection",
    "HarnessDetectionEnvironment",
    "HarnessDetectionKind",
    "HarnessDetectionState",
    "HarnessInstallCapability",
    "HarnessInstallPlan",
    "HarnessInstallPlanEntry",
    "HarnessSelectionMode",
    "HarnessSelectionStatus",
    "create_harness_install_plan",
    "dedupe_harness_names",
    "detect_available_harnesses",
    "find_command_on_path",
    "has_directory",
    "parse_harness_name",
    "parse_harness_overrides",
]
