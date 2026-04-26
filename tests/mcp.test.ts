import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { emitMcpConfig } from "../src/lib/emit.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await rm(directory, { recursive: true, force: true });
    }),
  );
});

describe("emitMcpConfig", () => {
  it("emits .mcp.json for claude-code with tilth, context7, and tavily entries", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);

    const mcpPath = path.join(outputRoot, ".mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers).toBeDefined();
    expect(config.mcpServers.tilth).toBeDefined();
    expect(config.mcpServers.context7).toBeDefined();
    expect(config.mcpServers.tavily).toBeDefined();
    expect(config.mcpServers.serper).toBeUndefined();
  });

  it("tilth entry has npx command with --mcp and --edit flags", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);

    const mcpPath = path.join(outputRoot, ".mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers.tilth.command).toBe("npx");
    expect(config.mcpServers.tilth.args).toContain("--mcp");
    expect(config.mcpServers.tilth.args).toContain("--edit");
  });

  it("tavily entry has TAVILY_API_KEY environment variable", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);

    const mcpPath = path.join(outputRoot, ".mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers.tavily.env).toBeDefined();
    expect(config.mcpServers.tavily.env.TAVILY_API_KEY).toBeDefined();
  });

  it("context7 entry uses the official npx package", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);

    const mcpPath = path.join(outputRoot, ".mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers.context7.command).toBe("npx");
    expect(config.mcpServers.context7.args).toEqual([
      "-y",
      "@upstash/context7-mcp",
    ]);
  });

  it("emits mcp.json (no leading dot) for cursor target", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("cursor", outputRoot);

    const mcpPath = path.join(outputRoot, "mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers).toBeDefined();
    expect(config.mcpServers.tilth).toBeDefined();
    expect(config.mcpServers.context7).toBeDefined();
  });

  it("includes milknado MCP server entry in output", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);

    const mcpPath = path.join(outputRoot, ".mcp.json");
    const content = await readFile(mcpPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers.milknado).toBeDefined();
    expect(config.mcpServers.milknado.command).toBeDefined();
    expect(content).toContain("milknado");
  });
});
