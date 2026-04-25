import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { emitPluginManifest } from "../src/lib/emit.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await rm(directory, { recursive: true, force: true });
    }),
  );
});

describe("emitPluginManifest", () => {
  it("emits valid .claude-plugin/plugin.json for claude-code target", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      name: "cheese-flow",
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
    };

    await emitPluginManifest("claude-code", metadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".claude-plugin", "plugin.json");
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow");
    expect(manifest.version).toBe("0.1.0");
    expect(manifest.author).toEqual({ name: "Cheese Lord" });
  });

  it("emits valid .claude-plugin/plugin.json for copilot-cli target", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      name: "cheese-flow",
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
    };

    await emitPluginManifest("copilot-cli", metadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".claude-plugin", "plugin.json");
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow");
  });

  it("emits valid .cursor-plugin/plugin.json for cursor target", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      name: "cheese-flow",
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
    };

    await emitPluginManifest("cursor", metadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".cursor-plugin", "plugin.json");
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow");
  });

  it("emits valid .codex-plugin/plugin.json for codex target", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      name: "cheese-flow",
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
    };

    await emitPluginManifest("codex", metadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".codex-plugin", "plugin.json");
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow");
  });

  it("includes homepage and keywords in codex manifest when supplied", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      name: "cheese-flow",
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
      homepage: "https://example.invalid/cheese",
      keywords: ["cheese", "flow"],
    };

    await emitPluginManifest("codex", metadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".codex-plugin", "plugin.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    expect(manifest.homepage).toBe("https://example.invalid/cheese");
    expect(manifest.keywords).toEqual(["cheese", "flow"]);
  });

  it("rejects metadata with missing required name field", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const invalidMetadata = {
      version: "0.1.0",
      description: "Multi-harness plugin compiler",
      author: { name: "Cheese Lord" },
      license: "MIT",
      repository: "https://github.com/paulnsorensen/cheese-flow",
    } as unknown;

    await expect(
      emitPluginManifest("claude-code", invalidMetadata as never, outputRoot),
    ).rejects.toThrow();
  });
});
