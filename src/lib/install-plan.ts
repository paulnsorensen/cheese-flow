import { harnessAdapters, harnessNames } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";
import {
  detectAvailableHarnesses,
  getHarnessInstallCapability,
  type HarnessDetection,
  type HarnessDetectionEnvironment,
  type HarnessInstallCapability,
} from "./harness-detection.js";

export type {
  HarnessDetection,
  HarnessDetectionEnvironment,
  HarnessDetectionKind,
  HarnessDetectionState,
  HarnessInstallCapability,
} from "./harness-detection.js";
export {
  detectAvailableHarnesses,
  findCommandOnPath,
  hasDirectory,
} from "./harness-detection.js";

export type HarnessSelectionMode = "auto-detect" | "explicit";
export type HarnessSelectionStatus = "selected" | "skipped";

export type HarnessInstallPlanEntry = {
  harness: HarnessName;
  displayName: string;
  outputRoot: string;
  selection: HarnessSelectionStatus;
  capability: HarnessInstallCapability;
  detection: HarnessDetection;
  reason: string;
};

export type HarnessInstallPlan = {
  selectionMode: HarnessSelectionMode;
  requestedHarnesses: HarnessName[];
  selectedHarnesses: HarnessName[];
  entries: HarnessInstallPlanEntry[];
  ok: boolean;
  guidance?: string;
};

type CreateHarnessInstallPlanOptions = {
  projectRoot: string;
  environment?: HarnessDetectionEnvironment;
  requestedHarnesses?: readonly HarnessName[];
};

type BuildPlanEntryOptions = {
  harness: HarnessName;
  selection: HarnessSelectionStatus;
  detection: HarnessDetection;
};

export function parseHarnessName(value: string): HarnessName {
  const trimmed = value.trim();
  if (harnessNames.includes(trimmed as HarnessName)) {
    return trimmed as HarnessName;
  }

  throw new Error(
    `Unsupported harness "${trimmed}". Expected one of: ${harnessNames.join(", ")}.`,
  );
}

export function dedupeHarnessNames(
  harnesses: readonly HarnessName[],
): HarnessName[] {
  const seen = new Set<HarnessName>();
  return harnesses.filter((harness) => {
    if (seen.has(harness)) return false;
    seen.add(harness);
    return true;
  });
}

export function parseHarnessOverrides(
  values: readonly string[],
): HarnessName[] {
  return dedupeHarnessNames(
    values.flatMap((value) => value.split(",").map(parseHarnessName)),
  );
}

export async function createHarnessInstallPlan(
  options: CreateHarnessInstallPlanOptions,
): Promise<HarnessInstallPlan> {
  const requestedHarnesses = dedupeHarnessNames(
    options.requestedHarnesses ?? [],
  );
  if (requestedHarnesses.length > 0) {
    return buildExplicitInstallPlan(requestedHarnesses);
  }

  return buildAutoDetectInstallPlan(
    await detectAvailableHarnesses(options),
    requestedHarnesses,
  );
}

function buildExplicitInstallPlan(
  requestedHarnesses: HarnessName[],
): HarnessInstallPlan {
  const requestedSet = new Set(requestedHarnesses);
  return {
    selectionMode: "explicit",
    requestedHarnesses,
    selectedHarnesses: requestedHarnesses,
    ok: true,
    entries: harnessNames.map((harness) =>
      buildPlanEntry({
        harness,
        selection: requestedSet.has(harness) ? "selected" : "skipped",
        detection: {
          state: "bypassed",
          reason: "Skipped auto-detect because --harness was provided.",
        },
      }),
    ),
  };
}

function buildAutoDetectInstallPlan(
  detections: Record<HarnessName, HarnessDetection>,
  requestedHarnesses: HarnessName[],
): HarnessInstallPlan {
  const selectedHarnesses = harnessNames.filter(
    (harness) => detections[harness].state === "detected",
  );
  const guidance =
    selectedHarnesses.length > 0
      ? undefined
      : 'No installed harnesses detected. Re-run with --harness <name> or use "cheese compile".';

  return {
    selectionMode: "auto-detect",
    requestedHarnesses,
    selectedHarnesses,
    ok: selectedHarnesses.length > 0,
    ...(guidance === undefined ? {} : { guidance }),
    entries: harnessNames.map((harness) =>
      buildPlanEntry({
        harness,
        selection:
          detections[harness].state === "detected" ? "selected" : "skipped",
        detection: detections[harness],
      }),
    ),
  };
}

function buildPlanEntry(
  options: BuildPlanEntryOptions,
): HarnessInstallPlanEntry {
  const adapter = harnessAdapters[options.harness];
  const selectedReason =
    options.detection.state === "bypassed"
      ? "Selected explicitly via --harness."
      : options.detection.reason;

  return {
    harness: options.harness,
    displayName: adapter.displayName,
    outputRoot: adapter.outputRoot,
    selection: options.selection,
    capability: getHarnessInstallCapability(options.harness),
    detection: options.detection,
    reason:
      options.selection === "selected"
        ? selectedReason
        : options.detection.state === "bypassed"
          ? "Skipped because it was not requested via --harness."
          : options.detection.reason,
  };
}
