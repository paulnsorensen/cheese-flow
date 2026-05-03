import { randomUUID } from "node:crypto";
import { chmod, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  detectAvailableHarnesses,
  findCommandOnPath,
  getHarnessInstallCapability,
} from "../src/lib/harness-detection.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function makeDirectory(prefix: string): Promise<string> {
  const directory = path.resolve(".test-runtime", `${prefix}-${randomUUID()}`);
  await mkdir(directory, { recursive: true });
  createdDirectories.push(directory);
  return directory;
}

async function writeExecutable(
  directory: string,
  name: string,
): Promise<string> {
  const filePath = path.join(directory, name);
  await writeFile(filePath, "#!/bin/sh\nexit 0\n", "utf8");
  await chmod(filePath, 0o755);
  return filePath;
}

async function withPlatform<T>(
  platform: NodeJS.Platform,
  run: () => Promise<T>,
): Promise<T> {
  const descriptor = Object.getOwnPropertyDescriptor(process, "platform");
  if (descriptor === undefined) {
    throw new Error("process.platform descriptor is unavailable");
  }

  Object.defineProperty(process, "platform", {
    configurable: true,
    value: platform,
  });
  try {
    return await run();
  } finally {
    Object.defineProperty(process, "platform", descriptor);
  }
}

function restoreEnv(
  name: "PATH" | "Path" | "PATHEXT",
  value: string | undefined,
): void {
  if (value === undefined) {
    delete process.env[name];
    return;
  }

  process.env[name] = value;
}

describe("getHarnessInstallCapability", () => {
  it("classifies harnesses by install capability", () => {
    expect(getHarnessInstallCapability("claude-code")).toBe("manual-capable");
    expect(getHarnessInstallCapability("cursor")).toBe("auto-install");
  });
});

describe("findCommandOnPath", () => {
  it("uses PATH first, then Path, and returns null when neither is set", async () => {
    const binDirectory = await makeDirectory("path-bin");
    const executablePath = await writeExecutable(binDirectory, "copilot");
    const originalPath = process.env.PATH;
    const originalWindowsPath = process.env.Path;

    try {
      process.env.PATH = binDirectory;
      delete process.env.Path;
      await expect(findCommandOnPath("copilot")).resolves.toBe(executablePath);

      delete process.env.PATH;
      process.env.Path = binDirectory;
      await expect(findCommandOnPath("copilot")).resolves.toBe(executablePath);

      delete process.env.Path;
      await expect(findCommandOnPath("copilot")).resolves.toBeNull();
    } finally {
      restoreEnv("PATH", originalPath);
      restoreEnv("Path", originalWindowsPath);
    }
  });

  it("applies win32 PATHEXT probes and preserves explicit extensions", async () => {
    const binDirectory = await makeDirectory("win-bin");
    const defaultExtensionPath = await writeExecutable(
      binDirectory,
      "codex.COM",
    );
    const explicitExtensionPath = await writeExecutable(
      binDirectory,
      "copilot.CMD",
    );
    const originalPathExt = process.env.PATHEXT;

    try {
      delete process.env.PATHEXT;
      await withPlatform("win32", async () => {
        await expect(findCommandOnPath("codex", binDirectory)).resolves.toBe(
          defaultExtensionPath,
        );
      });

      process.env.PATHEXT = ".EXE;.CMD";
      await withPlatform("win32", async () => {
        await expect(findCommandOnPath("copilot", binDirectory)).resolves.toBe(
          explicitExtensionPath,
        );
        await expect(
          findCommandOnPath("copilot.CMD", binDirectory),
        ).resolves.toBe(explicitExtensionPath);
      });
    } finally {
      restoreEnv("PATHEXT", originalPathExt);
    }
  });
});

describe("detectAvailableHarnesses", () => {
  it("uses default file-system and PATH probes when no environment override is provided", async () => {
    const projectRoot = await makeDirectory("project-root");
    const binDirectory = await makeDirectory("detect-bin");
    const detectedCommandPath = await writeExecutable(binDirectory, "copilot");
    const cursorSurface = path.join(projectRoot, ".cursor");
    const originalPath = process.env.PATH;
    const originalWindowsPath = process.env.Path;

    await mkdir(cursorSurface, { recursive: true });

    try {
      process.env.PATH = binDirectory;
      delete process.env.Path;

      const detections = await detectAvailableHarnesses({ projectRoot });

      expect(detections["copilot-cli"]).toMatchObject({
        state: "detected",
        kind: "cli",
        value: detectedCommandPath,
      });
      expect(detections.cursor).toMatchObject({
        state: "detected",
        kind: "surface",
        value: cursorSurface,
      });
      expect(detections["claude-code"]).toEqual({
        state: "not-detected",
        reason: 'No Claude Code CLI "claude" on PATH detected.',
      });
      expect(detections.codex).toEqual({
        state: "not-detected",
        reason: 'No Codex CLI "codex" on PATH detected.',
      });
    } finally {
      restoreEnv("PATH", originalPath);
      restoreEnv("Path", originalWindowsPath);
    }
  });
});
