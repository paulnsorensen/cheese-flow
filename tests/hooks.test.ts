import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emitHooks } from "../src/lib/emit.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await rm(directory, { recursive: true, force: true });
    }),
  );
  vi.clearAllMocks();
});

describe("emitHooks", () => {
  it("skips hook emission for cursor target with info log", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
    };

    const result = await emitHooks("cursor", source, outputRoot);

    expect(result).toBe(false);
  });

  it("emits hooks.json with camelCase keys for claude-code", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
      preToolUse: [{ type: "command", command: "echo pre" }],
    };

    await emitHooks("claude-code", source, outputRoot);

    const hooksPath = path.join(outputRoot, "hooks.json");
    const content = await readFile(hooksPath, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.sessionStart).toBeDefined();
    expect(config.hooks.preToolUse).toBeDefined();
  });

  it("emits hooks with PascalCase keys for codex", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
      preToolUse: [{ type: "command", command: "echo pre" }],
    };

    await emitHooks("codex", source, outputRoot);

    const hooksPath = path.join(outputRoot, "hooks.json");
    const content = await readFile(hooksPath, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.SessionStart).toBeDefined();
    expect(config.hooks.PreToolUse).toBeDefined();
    expect(config.hooks.SessionStart[0].matcher).toBeDefined();
    expect(config.hooks.SessionStart[0].hooks[0].timeout).toBe(600);
  });

  it("emits hooks with camelCase keys and version for copilot-cli", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
    };

    await emitHooks("copilot-cli", source, outputRoot);

    const hooksPath = path.join(outputRoot, "hooks.json");
    const content = await readFile(hooksPath, "utf8");
    const config = JSON.parse(content);

    expect(config.version).toBe(1);
    expect(config.hooks.sessionStart).toBeDefined();
  });

  it("skips entries that are explicitly undefined", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
      preToolUse: undefined,
    };

    await emitHooks("claude-code", source, outputRoot);

    const hooksPath = path.join(outputRoot, "hooks.json");
    const content = await readFile(hooksPath, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.sessionStart).toBeDefined();
    expect(config.hooks.preToolUse).toBeUndefined();
  });

  it("skips non-portable events with warn", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo start" }],
      sessionEnd: [{ type: "command", command: "echo end" }],
    };

    await emitHooks("claude-code", source, outputRoot);

    const hooksPath = path.join(outputRoot, "hooks.json");
    const content = await readFile(hooksPath, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.sessionStart).toBeDefined();
    expect(config.hooks.sessionEnd).toBeUndefined();
  });
});
