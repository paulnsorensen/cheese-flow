import { constants } from "node:fs";
import { access, stat } from "node:fs/promises";
import path, { delimiter } from "node:path";
import { harnessAdapters, harnessNames } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";

export type HarnessInstallCapability =
  | "auto-install"
  | "manual-capable"
  | "unsupported";
export type HarnessDetectionState = "detected" | "not-detected" | "bypassed";
export type HarnessDetectionKind = "cli" | "surface";

export type HarnessDetection = {
  state: HarnessDetectionState;
  kind?: HarnessDetectionKind;
  value?: string;
  reason: string;
};

export type HarnessDetectionEnvironment = {
  findCommand?: (command: string) => Promise<string | null>;
  hasDirectory?: (directoryPath: string) => Promise<boolean>;
};

type CliProbe = {
  kind: "cli";
  command: string;
};

type SurfaceProbe = {
  kind: "surface";
  relativePath: string;
};

type HarnessDetectionProbe = CliProbe | SurfaceProbe;

type HarnessInstallProfile = {
  capability: HarnessInstallCapability;
  probes: readonly HarnessDetectionProbe[];
};

const harnessInstallProfiles = {
  "claude-code": {
    capability: "manual-capable",
    probes: [{ kind: "cli", command: "claude" }],
  },
  codex: {
    capability: "manual-capable",
    probes: [{ kind: "cli", command: "codex" }],
  },
  cursor: {
    capability: "auto-install",
    probes: [{ kind: "surface", relativePath: ".cursor" }],
  },
  "copilot-cli": {
    capability: "auto-install",
    probes: [{ kind: "cli", command: "copilot" }],
  },
} satisfies Record<HarnessName, HarnessInstallProfile>;

type DetectHarnessesOptions = {
  projectRoot: string;
  environment?: HarnessDetectionEnvironment;
};

type DetectHarnessOptions = {
  harness: HarnessName;
  projectRoot: string;
  findCommand: (command: string) => Promise<string | null>;
  hasDirectory: (directoryPath: string) => Promise<boolean>;
};

export function getHarnessInstallCapability(
  harness: HarnessName,
): HarnessInstallCapability {
  return harnessInstallProfiles[harness].capability;
}

export async function findCommandOnPath(
  command: string,
  searchPath = process.env.PATH ?? process.env.Path ?? "",
): Promise<string | null> {
  const directories = searchPath.split(delimiter).filter(Boolean);
  const extensions = process.platform === "win32" ? pathExtensions() : [""];

  for (const directory of directories) {
    for (const extension of extensions) {
      const candidate = path.join(directory, withExtension(command, extension));
      try {
        await access(candidate, constants.X_OK);
        return candidate;
      } catch {}
    }
  }

  return null;
}

export async function hasDirectory(directoryPath: string): Promise<boolean> {
  try {
    const stats = await stat(directoryPath);
    return stats.isDirectory();
  } catch {
    return false;
  }
}

export async function detectAvailableHarnesses(
  options: DetectHarnessesOptions,
): Promise<Record<HarnessName, HarnessDetection>> {
  const findCommand = options.environment?.findCommand ?? findCommandOnPath;
  const checkDirectory = options.environment?.hasDirectory ?? hasDirectory;
  const detections = await Promise.all(
    harnessNames.map(async (harness) => [
      harness,
      await detectHarness({
        harness,
        projectRoot: options.projectRoot,
        findCommand,
        hasDirectory: checkDirectory,
      }),
    ]),
  );

  return Object.fromEntries(detections) as Record<
    HarnessName,
    HarnessDetection
  >;
}

async function detectHarness(
  options: DetectHarnessOptions,
): Promise<HarnessDetection> {
  const displayName = harnessAdapters[options.harness].displayName;
  const probes = harnessInstallProfiles[options.harness].probes;

  for (const probe of probes) {
    if (probe.kind === "cli") {
      const commandPath = await options.findCommand(probe.command);
      if (commandPath !== null) {
        return {
          state: "detected",
          kind: "cli",
          value: commandPath,
          reason: `Auto-detected ${displayName} via CLI "${probe.command}".`,
        };
      }
      continue;
    }

    const directoryPath = path.join(options.projectRoot, probe.relativePath);
    if (await options.hasDirectory(directoryPath)) {
      return {
        state: "detected",
        kind: "surface",
        value: directoryPath,
        reason: `Auto-detected ${displayName} via ${probe.relativePath}/.`,
      };
    }
  }

  return {
    state: "not-detected",
    reason: `No ${displayName} ${describeProbes(probes)} detected.`,
  };
}

function describeProbes(probes: readonly HarnessDetectionProbe[]): string {
  return probes.map(describeProbe).join(" or ");
}

function describeProbe(probe: HarnessDetectionProbe): string {
  return probe.kind === "cli"
    ? `CLI "${probe.command}" on PATH`
    : `project surface "${probe.relativePath}"`;
}

function pathExtensions(): string[] {
  const configured = process.env.PATHEXT ?? ".EXE;.CMD;.BAT;.COM";
  return configured.split(";").filter(Boolean);
}

function withExtension(command: string, extension: string): string {
  if (
    process.platform === "win32" &&
    command.toLowerCase().endsWith(extension.toLowerCase())
  ) {
    return command;
  }

  return `${command}${extension}`;
}
