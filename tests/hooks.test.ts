import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { harnessAdapters } from "../src/adapters/index.js";
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

  it("emits sessionStart bootstrap entry for every bootstrapHook=true harness", async () => {
    const source = {
      sessionStart: [
        { type: "command", command: "bash hooks/cheese-bootstrap.sh" },
      ],
    };
    const enabled: Array<keyof typeof harnessAdapters> = [
      "claude-code",
      "codex",
      "copilot-cli",
    ];
    for (const harness of enabled) {
      const caps = harnessAdapters[harness].capabilities as {
        bootstrapHook?: boolean;
      };
      expect(
        caps.bootstrapHook,
        `${harness} must have bootstrapHook=true`,
      ).toBe(true);

      const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
      createdDirectories.push(outputRoot);

      const result = await emitHooks(harness, source, outputRoot);
      expect(result, `${harness} should emit hooks.json`).not.toBe(false);

      const hooksPath = path.join(outputRoot, "hooks.json");
      const content = await readFile(hooksPath, "utf8");
      expect(content).toContain("cheese-bootstrap.sh");
    }
  });

  it("places bootstrap command at the structurally correct path per harness", async () => {
    const source = {
      sessionStart: [
        { type: "command", command: "bash hooks/cheese-bootstrap.sh" },
      ],
    };

    const claudeRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(claudeRoot);
    await emitHooks("claude-code", source, claudeRoot);
    const claudeConfig = JSON.parse(
      await readFile(path.join(claudeRoot, "hooks.json"), "utf8"),
    ) as {
      hooks: { sessionStart: Array<{ type: string; command: string }> };
    };
    expect(claudeConfig.hooks.sessionStart).toHaveLength(1);
    expect(claudeConfig.hooks.sessionStart[0]?.type).toBe("command");
    expect(claudeConfig.hooks.sessionStart[0]?.command).toBe(
      "bash hooks/cheese-bootstrap.sh",
    );

    const codexRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(codexRoot);
    await emitHooks("codex", source, codexRoot);
    const codexConfig = JSON.parse(
      await readFile(path.join(codexRoot, "hooks.json"), "utf8"),
    ) as {
      hooks: {
        SessionStart: Array<{
          matcher: string;
          hooks: Array<{ type: string; command: string; timeout: number }>;
        }>;
      };
    };
    expect(codexConfig.hooks.SessionStart).toHaveLength(1);
    expect(codexConfig.hooks.SessionStart[0]?.matcher).toBe("*");
    expect(codexConfig.hooks.SessionStart[0]?.hooks[0]?.command).toBe(
      "bash hooks/cheese-bootstrap.sh",
    );

    const copilotRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(copilotRoot);
    await emitHooks("copilot-cli", source, copilotRoot);
    const copilotConfig = JSON.parse(
      await readFile(path.join(copilotRoot, "hooks.json"), "utf8"),
    ) as {
      version: number;
      hooks: { sessionStart: Array<{ type: string; command: string }> };
    };
    expect(copilotConfig.version).toBe(1);
    expect(copilotConfig.hooks.sessionStart).toHaveLength(1);
    expect(copilotConfig.hooks.sessionStart[0]?.command).toBe(
      "bash hooks/cheese-bootstrap.sh",
    );
  });

  it("skips emission for cursor (bootstrapHook=false)", async () => {
    const cursorCaps = harnessAdapters.cursor.capabilities as {
      bootstrapHook?: boolean;
    };
    expect(cursorCaps.bootstrapHook).toBe(false);

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [
        { type: "command", command: "bash hooks/cheese-bootstrap.sh" },
      ],
    };
    const result = await emitHooks("cursor", source, outputRoot);
    expect(result).toBe(false);
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
