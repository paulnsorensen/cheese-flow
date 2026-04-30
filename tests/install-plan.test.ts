import path from "node:path";
import { describe, expect, it } from "vitest";
import type { HarnessName } from "../src/domain/harness.js";
import {
  createHarnessInstallPlan,
  findCommandOnPath,
  type HarnessDetectionEnvironment,
  type HarnessInstallPlan,
  hasDirectory,
  parseHarnessOverrides,
} from "../src/lib/install-plan.js";

function makeEnvironment(options: {
  commands?: string[];
  surfaces?: string[];
}): HarnessDetectionEnvironment {
  const commands = new Set(options.commands ?? []);
  const surfaces = new Set(options.surfaces ?? []);

  return {
    findCommand: async (command) =>
      commands.has(command) ? path.join("/mock/bin", command) : null,
    hasDirectory: async (directoryPath) => surfaces.has(directoryPath),
  };
}

function getEntry(plan: HarnessInstallPlan, harness: HarnessName) {
  const entry = plan.entries.find((candidate) => candidate.harness === harness);
  if (entry === undefined) {
    throw new Error(`Missing plan entry for ${harness}`);
  }
  return entry;
}

describe("findCommandOnPath", () => {
  it("finds commands that are already on PATH", async () => {
    await expect(findCommandOnPath("node")).resolves.toEqual(
      expect.any(String),
    );
  });
});

describe("hasDirectory", () => {
  it("detects directories on disk", async () => {
    await expect(hasDirectory(path.resolve("src"))).resolves.toBe(true);
    await expect(
      hasDirectory(path.resolve("missing-install-plan-directory")),
    ).resolves.toBe(false);
  });
});

describe("createHarnessInstallPlan", () => {
  it("auto-detects a single manual-capable harness from its CLI", async () => {
    const plan = await createHarnessInstallPlan({
      projectRoot: "/workspace",
      environment: makeEnvironment({ commands: ["claude"] }),
    });

    expect(plan.selectionMode).toBe("auto-detect");
    expect(plan.ok).toBe(true);
    expect(plan.selectedHarnesses).toEqual(["claude-code"]);

    expect(getEntry(plan, "claude-code")).toMatchObject({
      selection: "selected",
      capability: "manual-capable",
      detection: {
        state: "detected",
        kind: "cli",
        value: path.join("/mock/bin", "claude"),
      },
    });
    expect(getEntry(plan, "codex").selection).toBe("skipped");
  });

  it("auto-detects multiple harnesses from CLI and project surfaces", async () => {
    const projectRoot = "/workspace";
    const plan = await createHarnessInstallPlan({
      projectRoot,
      environment: makeEnvironment({
        commands: ["copilot"],
        surfaces: [path.join(projectRoot, ".cursor")],
      }),
    });

    expect(plan.selectionMode).toBe("auto-detect");
    expect(plan.ok).toBe(true);
    expect(plan.selectedHarnesses).toEqual(["cursor", "copilot-cli"]);
    expect(getEntry(plan, "cursor")).toMatchObject({
      selection: "selected",
      capability: "auto-install",
      detection: {
        state: "detected",
        kind: "surface",
        value: path.join(projectRoot, ".cursor"),
      },
    });
    expect(getEntry(plan, "copilot-cli")).toMatchObject({
      selection: "selected",
      capability: "auto-install",
      detection: {
        state: "detected",
        kind: "cli",
        value: path.join("/mock/bin", "copilot"),
      },
    });
  });

  it("preserves explicit harness order after dedupe and bypasses auto-detect", async () => {
    const requestedHarnesses = parseHarnessOverrides([
      "copilot-cli,cursor",
      "copilot-cli",
      "claude-code,cursor",
    ]);
    const plan = await createHarnessInstallPlan({
      projectRoot: "/workspace",
      requestedHarnesses,
      environment: makeEnvironment({ commands: ["codex"] }),
    });

    expect(requestedHarnesses).toEqual([
      "copilot-cli",
      "cursor",
      "claude-code",
    ]);
    expect(plan.selectionMode).toBe("explicit");
    expect(plan.ok).toBe(true);
    expect(plan.selectedHarnesses).toEqual(requestedHarnesses);
    expect(getEntry(plan, "copilot-cli")).toMatchObject({
      selection: "selected",
      capability: "auto-install",
      detection: { state: "bypassed" },
    });
    expect(getEntry(plan, "claude-code")).toMatchObject({
      selection: "selected",
      capability: "manual-capable",
      detection: { state: "bypassed" },
    });
    expect(getEntry(plan, "codex")).toMatchObject({
      selection: "skipped",
      detection: { state: "bypassed" },
    });
  });

  it("returns guidance when auto-detect finds no harnesses", async () => {
    const plan = await createHarnessInstallPlan({
      projectRoot: "/workspace",
      environment: makeEnvironment({}),
    });

    expect(plan.selectionMode).toBe("auto-detect");
    expect(plan.ok).toBe(false);
    expect(plan.selectedHarnesses).toEqual([]);
    expect(plan.guidance).toContain("--harness <name>");
    expect(plan.guidance).toContain("cheese compile");
    expect(plan.entries.every((entry) => entry.selection === "skipped")).toBe(
      true,
    );
  });
});

describe("parseHarnessOverrides", () => {
  it("rejects unsupported harness names", () => {
    expect(() => parseHarnessOverrides(["bogus"])).toThrow(
      /Unsupported harness/u,
    );
  });
});
