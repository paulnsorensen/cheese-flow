import { execFile } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";
import {
  installHarnessArtifacts,
  previewAgent,
  readSkill,
} from "../src/lib/compiler.js";
import { parseFrontmatter } from "../src/lib/frontmatter.js";
import {
  parseAgentFrontmatter,
  parseSkillFrontmatter,
  resolveModel,
} from "../src/lib/schemas.js";

const createdDirectories: string[] = [];
const execFileAsync = promisify(execFile);

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("installHarnessArtifacts", () => {
  it("compiles the basic agent template for Claude Code and Codex", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const outputs = await installHarnessArtifacts({
      projectRoot,
      harnesses: ["claude-code", "codex"],
    });

    expect(outputs).toHaveLength(2);

    const claudeAgent = await readFile(
      path.join(projectRoot, ".claude", "agents", "basic-agent.md"),
      "utf8",
    );
    const codexAgent = await readFile(
      path.join(projectRoot, ".codex", "agents", "basic-agent.md"),
      "utf8",
    );

    expect(claudeAgent).toContain("claude-sonnet-4-5");
    expect(codexAgent).toContain("gpt-5.1-codex");

    // New emitters: plugin manifest + mcp config appear for both harnesses
    const claudePlugin = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ) as { name: string };
    expect(claudePlugin.name).toBe("cheese-flow");

    const claudeMcp = JSON.parse(
      await readFile(path.join(projectRoot, ".claude", ".mcp.json"), "utf8"),
    ) as { mcpServers: Record<string, unknown> };
    expect(claudeMcp.mcpServers).toHaveProperty("tilth");
    expect(claudeMcp.mcpServers).toHaveProperty("context7");
    expect(claudeMcp.mcpServers).toHaveProperty("tavily");
    expect(claudeMcp.mcpServers).not.toHaveProperty("serper");

    const codexPlugin = JSON.parse(
      await readFile(
        path.join(projectRoot, ".codex", ".codex-plugin", "plugin.json"),
        "utf8",
      ),
    ) as { name: string };
    expect(codexPlugin.name).toBe("cheese-flow");

    const codexMcp = JSON.parse(
      await readFile(path.join(projectRoot, ".codex", ".mcp.json"), "utf8"),
    ) as { mcpServers: Record<string, unknown> };
    expect(codexMcp.mcpServers).toHaveProperty("tilth");
    expect(codexMcp.mcpServers).toHaveProperty("context7");
  });

  it("validates the shipped skill metadata", async () => {
    const skill = await readSkill(path.resolve("."), "basic-skill");
    expect(skill.name).toBe("basic-skill");
    expect(skill.description).toContain("portable");
  });

  it("renders a preview from the template source", async () => {
    const output = await previewAgent(
      path.resolve("."),
      "basic-agent.md.eta",
      "claude-code",
    );
    expect(output).toContain("Harness target: Claude Code");
  });

  it("rejects skills whose folder name does not match the spec name", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-invalid-"),
    );
    createdDirectories.push(projectRoot);
    await mkdir(path.join(projectRoot, "agents"), { recursive: true });
    await mkdir(path.join(projectRoot, "skills", "wrong-name"), {
      recursive: true,
    });
    await cp(
      path.resolve("agents", "basic-agent.md.eta"),
      path.join(projectRoot, "agents", "basic-agent.md.eta"),
    );

    await writeFile(
      path.join(projectRoot, "skills", "wrong-name", "SKILL.md"),
      `---\nname: basic-skill\ndescription: Portable test skill\n---\n# Wrong\n`,
      "utf8",
    );

    await expect(
      installHarnessArtifacts({
        projectRoot,
        harnesses: ["claude-code"],
      }),
    ).rejects.toThrow(/must match frontmatter name/u);
  });

  it("ignores non-template agent files and non-directory skill entries", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-extra-files-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });
    await mkdir(path.join(projectRoot, "skills", "nested-dir"), {
      recursive: true,
    });

    await writeFile(
      path.join(projectRoot, "agents", "README.txt"),
      "ignore me\n",
      "utf8",
    );
    await writeFile(
      path.join(projectRoot, "skills", "notes.txt"),
      "ignore me\n",
      "utf8",
    );
    await writeFile(
      path.join(projectRoot, "skills", "nested-dir", "SKILL.md"),
      `---\nname: nested-dir\ndescription: Another portable skill\n---\n# Nested\n`,
      "utf8",
    );

    await installHarnessArtifacts({
      projectRoot,
      harnesses: ["claude-code"],
    });

    const manifest = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", "manifest.json"),
        "utf8",
      ),
    ) as { agents: string[]; skills: string[]; commands: string[] };

    expect(manifest.agents).toContain("basic-agent.md");
    expect(manifest.agents).not.toContain("README.txt");
    expect(manifest.skills).toContain("basic-skill");
    expect(manifest.skills).toContain("nested-dir");
    expect(manifest.skills).not.toContain("notes.txt");
    expect(manifest.commands).toEqual([]);
  });

  it("emits dual-surface artifacts and manifests for cursor", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-cursor-"),
    );
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
    });

    await installHarnessArtifacts({ projectRoot, harnesses: ["cursor"] });

    const cursorRoot = path.join(projectRoot, ".cursor");

    // Dual-surface: rule and command for the basic-skill
    const rule = await readFile(
      path.join(cursorRoot, "rules", "basic-skill.mdc"),
      "utf8",
    );
    const command = await readFile(
      path.join(cursorRoot, "commands", "basic-skill.md"),
      "utf8",
    );
    expect(rule).toContain("alwaysApply: false");
    expect(rule).toContain("description:");
    expect(command).toBeTruthy();

    // Plugin manifest at .cursor-plugin/plugin.json
    const pluginJson = JSON.parse(
      await readFile(
        path.join(cursorRoot, ".cursor-plugin", "plugin.json"),
        "utf8",
      ),
    ) as { name: string };
    expect(pluginJson.name).toBe("cheese-flow");

    // MCP config at mcp.json (no leading dot for cursor)
    const mcpJson = JSON.parse(
      await readFile(path.join(cursorRoot, "mcp.json"), "utf8"),
    ) as { mcpServers: Record<string, unknown> };
    expect(mcpJson.mcpServers).toHaveProperty("tilth");
    expect(mcpJson.mcpServers).toHaveProperty("context7");
    expect(mcpJson.mcpServers).toHaveProperty("tavily");
  });

  it("emits plugin manifest, mcp config, and hooks for copilot-cli", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-copilot-"),
    );
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
    });

    // Write an inline hooks.json source
    await writeFile(
      path.join(projectRoot, "hooks.json"),
      JSON.stringify({
        sessionStart: [{ type: "command", command: "echo start" }],
      }),
      "utf8",
    );

    await installHarnessArtifacts({ projectRoot, harnesses: ["copilot-cli"] });

    const copilotRoot = path.join(projectRoot, ".copilot");

    // Plugin manifest at .claude-plugin/plugin.json (copilot reuses same path)
    const pluginJson = JSON.parse(
      await readFile(
        path.join(copilotRoot, ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ) as { name: string; category?: string };
    expect(pluginJson.name).toBe("cheese-flow");
    expect(pluginJson.category).toBe("development");

    // MCP config
    const mcpJson = JSON.parse(
      await readFile(path.join(copilotRoot, ".mcp.json"), "utf8"),
    ) as { mcpServers: Record<string, unknown> };
    expect(mcpJson.mcpServers).toHaveProperty("tilth");
    expect(mcpJson.mcpServers).toHaveProperty("context7");

    // Hooks file with version:1 and camelCase keys
    const hooksJson = JSON.parse(
      await readFile(path.join(copilotRoot, "hooks.json"), "utf8"),
    ) as { version: number; hooks: Record<string, unknown> };
    expect(hooksJson.version).toBe(1);
    expect(hooksJson.hooks).toHaveProperty("sessionStart");
  });

  it("emits hooks from hooks.json source into each non-cursor harness", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-hooks-"),
    );
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
    });

    await writeFile(
      path.join(projectRoot, "hooks.json"),
      JSON.stringify({
        preToolUse: [{ type: "command", command: "echo pre" }],
        postToolUse: [{ type: "command", command: "echo post" }],
      }),
      "utf8",
    );

    await installHarnessArtifacts({
      projectRoot,
      harnesses: ["claude-code", "codex"],
    });

    // claude-code: camelCase hooks
    const claudeHooks = JSON.parse(
      await readFile(path.join(projectRoot, ".claude", "hooks.json"), "utf8"),
    ) as { hooks: Record<string, unknown> };
    expect(claudeHooks.hooks).toHaveProperty("preToolUse");
    expect(claudeHooks.hooks).toHaveProperty("postToolUse");

    // codex: PascalCase hooks with matcher wrapper
    const codexHooks = JSON.parse(
      await readFile(path.join(projectRoot, ".codex", "hooks.json"), "utf8"),
    ) as { hooks: Record<string, unknown> };
    expect(codexHooks.hooks).toHaveProperty("PreToolUse");
    expect(codexHooks.hooks).toHaveProperty("PostToolUse");
  });

  it("reads plugin metadata from .claude-plugin/plugin.json when present", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-plugin-meta-"),
    );
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp, mkdir: mkd }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
      await mkd(path.join(projectRoot, ".claude-plugin"), { recursive: true });
    });

    const customMeta = {
      name: "my-custom-plugin",
      version: "2.0.0",
      description: "Custom plugin description.",
      author: { name: "Test Author" },
      license: "Apache-2.0",
      repository: "https://github.com/test/repo",
      homepage: "https://example.com",
      keywords: ["test", "plugin"],
    };

    await writeFile(
      path.join(projectRoot, ".claude-plugin", "plugin.json"),
      JSON.stringify(customMeta),
      "utf8",
    );

    await installHarnessArtifacts({ projectRoot, harnesses: ["claude-code"] });

    const pluginJson = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ) as { name: string; homepage?: string; keywords?: string[] };

    expect(pluginJson.name).toBe("my-custom-plugin");
    expect(pluginJson.homepage).toBe("https://example.com");
    expect(pluginJson.keywords).toEqual(["test", "plugin"]);
  });

  it("rethrows non-ENOENT errors when reading plugin metadata", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp, mkdir }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
      // Create plugin.json as a directory to trigger EISDIR
      await mkdir(path.join(projectRoot, ".claude-plugin", "plugin.json"), {
        recursive: true,
      });
    });

    await expect(
      installHarnessArtifacts({ projectRoot, harnesses: ["claude-code"] }),
    ).rejects.toThrow();
  });

  it("rethrows non-ENOENT errors when reading hooks.json", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp, mkdir }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
      // Create hooks.json as a directory to trigger EISDIR
      await mkdir(path.join(projectRoot, "hooks.json"), { recursive: true });
    });

    await expect(
      installHarnessArtifacts({ projectRoot, harnesses: ["claude-code"] }),
    ).rejects.toThrow();
  });

  it("keeps help on -h and uses -H for harness selection", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "install", "--help"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain("-h, --help");
    expect(stdout).toContain("-H, --harness <name...>");
  });
});

describe("frontmatter and schema helpers", () => {
  it("parses frontmatter and falls back to the default model when needed", () => {
    const parsed = parseFrontmatter<{ name: string; description: string }>(
      "---\nname: example\ndescription: Parser test\n---\n# Body\n",
    );

    expect(parsed.data.name).toBe("example");
    expect(parsed.body.trim()).toBe("# Body");
    expect(
      resolveModel(
        {
          default: "gpt-5.1-codex",
        },
        "claude-code",
      ),
    ).toBe("gpt-5.1-codex");
  });

  it("rejects invalid frontmatter input", () => {
    expect(() => parseFrontmatter("no frontmatter here")).toThrow(
      /Expected YAML frontmatter/u,
    );
    expect(() => parseFrontmatter("---\nname: [oops\n---\nbody\n")).toThrow();
  });

  it("validates allowed tool field variants for skills and default tools for agents", () => {
    const skill = parseSkillFrontmatter({
      name: "basic-skill",
      description: "Portable skill",
      "allowed-tools": "read write",
    });
    const agent = parseAgentFrontmatter({
      name: "basic-agent",
      description: "Portable agent",
      models: {
        default: "gpt-5.1-codex",
      },
    });

    expect(skill["allowed-tools"]).toBe("read write");
    expect(agent.tools).toEqual([]);
  });
});
