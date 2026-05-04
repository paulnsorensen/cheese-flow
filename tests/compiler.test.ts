import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  access,
  cp,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";
import {
  compileHarnessBundle,
  compileHarnessBundles,
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

async function makeRuntimeDirectory(prefix: string): Promise<string> {
  const directory = path.resolve(".test-runtime", `${prefix}-${randomUUID()}`);
  await mkdir(directory, { recursive: true });
  createdDirectories.push(directory);
  return directory;
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

describe("compileHarnessBundles", () => {
  it("compiles the basic agent template for Claude Code and Codex", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const outputs = await compileHarnessBundles({
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

    expect(parseFrontmatter<{ model: string }>(claudeAgent).data.model).toBe(
      "sonnet",
    );
    expect(parseFrontmatter<{ model: string }>(codexAgent).data.model).toBe(
      "gpt-5-codex",
    );

    // New emitters: plugin manifest + mcp config appear for both harnesses
    const claudePlugin = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ) as {
      name: string;
      agents?: string;
      skills?: string;
      commands?: string;
      hooks?: string;
      mcpServers?: string;
    };
    expect(claudePlugin.name).toBe("cheese-flow");
    expect(claudePlugin.agents).toBe("./agents/");
    expect(claudePlugin.skills).toBe("./skills/");
    expect(claudePlugin.commands).toBeUndefined();
    expect(claudePlugin.hooks).toBe("./hooks.json");
    expect(claudePlugin.mcpServers).toBe("./.mcp.json");

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
    ) as {
      name: string;
      skills?: string;
      mcpServers?: string;
      agents?: string;
      commands?: string;
      hooks?: string;
    };
    expect(codexPlugin.name).toBe("cheese-flow");
    expect(codexPlugin.skills).toBe("./skills/");
    expect(codexPlugin.mcpServers).toBe("./.mcp.json");
    expect(codexPlugin.agents).toBeUndefined();
    expect(codexPlugin.commands).toBeUndefined();
    expect(codexPlugin.hooks).toBeUndefined();

    const codexMcp = JSON.parse(
      await readFile(path.join(projectRoot, ".codex", ".mcp.json"), "utf8"),
    ) as { mcpServers: Record<string, unknown> };
    expect(codexMcp.mcpServers).toHaveProperty("tilth");
    expect(codexMcp.mcpServers).toHaveProperty("context7");
  });

  it("compiles a single harness bundle and returns its metadata", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-single-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const compiled = await compileHarnessBundle({
      projectRoot,
      harness: "claude-code",
    });

    expect(compiled.harness).toBe("claude-code");
    expect(compiled.outputRoot).toBe(path.join(projectRoot, ".claude"));
    expect(compiled.pluginMetadata.name).toBe("cheese-flow");
    await expect(
      readFile(
        path.join(compiled.outputRoot, ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ).resolves.toContain('"name": "cheese-flow"');
  });

  it("emits agent frontmatter with skills binding for claude-code", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-claude-fm-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    const cookAgent = await readFile(
      path.join(projectRoot, ".claude", "agents", "cook.md"),
      "utf8",
    );
    const { data } = parseFrontmatter<{
      name: string;
      description: string;
      model: string;
      tools: string[];
      skills: string[];
      color: string;
      permissionMode: string;
    }>(cookAgent);
    expect(data.name).toBe("cook");
    expect(data.model).toBe("sonnet");
    expect(data.skills).toEqual(["cheez-read", "cheez-search", "cheez-write"]);
    expect(data.color).toBe("blue");
    expect(data.permissionMode).toBe("acceptEdits");
    expect(cookAgent).not.toContain("Required skills (prompt contract)");
  });

  it("drops claude-only fields and appends a skills prompt contract for codex", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-codex-fm-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["codex"],
    });

    const cookAgent = await readFile(
      path.join(projectRoot, ".codex", "agents", "cook.md"),
      "utf8",
    );
    const { data } = parseFrontmatter<{
      name: string;
      description: string;
      model: string;
      tools: string[];
      skills?: string[];
      color?: string;
      permissionMode?: string;
    }>(cookAgent);
    expect(data.name).toBe("cook");
    expect(data.model).toBe("gpt-5-codex");
    expect(data.skills).toBeUndefined();
    expect(data.color).toBeUndefined();
    expect(data.permissionMode).toBeUndefined();
    expect(cookAgent).toContain("Required skills (prompt contract)");
    expect(cookAgent).toContain("- cheez-read");
    expect(cookAgent).toContain("- cheez-search");
    expect(cookAgent).toContain("- cheez-write");
  });

  it("applies models.yaml pins and overrides during install", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-manifest-install-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });
    await writeFile(
      path.join(projectRoot, "models.yaml"),
      [
        "pins:",
        "  claude-code:",
        "    sonnet: claude-sonnet-4-6",
        "overrides:",
        "  basic-agent:",
        "    claude-code: claude-opus-4-7",
        "",
      ].join("\n"),
      "utf8",
    );

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    const cookAgent = await readFile(
      path.join(projectRoot, ".claude", "agents", "cook.md"),
      "utf8",
    );
    const cook = parseFrontmatter<{ model: string }>(cookAgent);
    expect(cook.data.model).toBe("claude-sonnet-4-6");

    const basicAgent = await readFile(
      path.join(projectRoot, ".claude", "agents", "basic-agent.md"),
      "utf8",
    );
    const basic = parseFrontmatter<{ model: string }>(basicAgent);
    expect(basic.data.model).toBe("claude-opus-4-7");
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
      compileHarnessBundles({
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

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    const manifest = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", "manifest.json"),
        "utf8",
      ),
    ) as { agents: string[]; skills: string[]; commands: string[] };

    expect(manifest.agents).toEqual([
      "age-assertions.md",
      "age-complexity.md",
      "age-correctness.md",
      "age-deslop.md",
      "age-encapsulation.md",
      "age-nih.md",
      "age-precedent.md",
      "age-security.md",
      "age-spec.md",
      "assertion-review.md",
      "basic-agent.md",
      "cleanup-wolf.md",
      "cook.md",
      "cut.md",
      "milknado-executor.md",
      "milknado-planner.md",
      "nih-scanner.md",
      "press.md",
      "taste-readability.md",
      "taste-scope.md",
      "taste-spec.md",
    ]);
    expect(manifest.skills).toEqual([
      "age",
      "basic-skill",
      "cheez-read",
      "cheez-search",
      "cheez-write",
      "cleanup",
      "cure",
      "gh",
      "merge-resolve",
      "milknado-execute",
      "milknado-plan",
      "mold",
      "nested-dir",
      "nih-audit",
      "research",
    ]);
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

    await compileHarnessBundles({ projectRoot, harnesses: ["cursor"] });

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
    ) as {
      name: string;
      rules?: string;
      skills?: string;
      agents?: string;
      commands?: string;
      hooks?: string;
      mcpServers?: string;
    };
    expect(pluginJson.name).toBe("cheese-flow");
    expect(pluginJson.rules).toBe("./rules/");
    expect(pluginJson.skills).toBe("./skills/");
    expect(pluginJson.agents).toBe("./agents/");
    expect(pluginJson.commands).toBe("./commands/");
    expect(pluginJson.hooks).toBeUndefined();
    expect(pluginJson.mcpServers).toBe("./mcp.json");

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

    await compileHarnessBundles({ projectRoot, harnesses: ["copilot-cli"] });

    const copilotRoot = path.join(projectRoot, ".copilot");

    // Plugin manifest at .claude-plugin/plugin.json (copilot reuses same path)
    const pluginJson = JSON.parse(
      await readFile(
        path.join(copilotRoot, ".claude-plugin", "plugin.json"),
        "utf8",
      ),
    ) as {
      name: string;
      category?: string;
      agents?: string;
      skills?: string;
      hooks?: string;
      mcpServers?: string;
      commands?: string;
    };
    expect(pluginJson.name).toBe("cheese-flow");
    expect(pluginJson.category).toBe("development");
    expect(pluginJson.agents).toBe("./agents/");
    expect(pluginJson.skills).toBe("./skills/");
    expect(pluginJson.hooks).toBe("./hooks.json");
    expect(pluginJson.mcpServers).toBe("./.mcp.json");
    expect(pluginJson.commands).toBeUndefined();

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

    await compileHarnessBundles({
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

    await compileHarnessBundles({ projectRoot, harnesses: ["claude-code"] });

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
      compileHarnessBundles({ projectRoot, harnesses: ["claude-code"] }),
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
      compileHarnessBundles({ projectRoot, harnesses: ["claude-code"] }),
    ).rejects.toThrow();
  });

  it("preserves user-managed files at the harness output root across rebuilds", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-preserve-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const claudeRoot = path.join(projectRoot, ".claude");
    await mkdir(claudeRoot, { recursive: true });
    const userSettingsPath = path.join(claudeRoot, "settings.local.json");
    const userClaudeMdPath = path.join(claudeRoot, "CLAUDE.md");
    await writeFile(userSettingsPath, '{"theme":"dark"}\n', "utf8");
    await writeFile(userClaudeMdPath, "# user notes\n", "utf8");

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });
    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    expect(await readFile(userSettingsPath, "utf8")).toBe('{"theme":"dark"}\n');
    expect(await readFile(userClaudeMdPath, "utf8")).toBe("# user notes\n");
  });

  it("removes stale generated agents on rebuild", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-stale-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    const staleAgentPath = path.join(
      projectRoot,
      ".claude",
      "agents",
      "renamed-away.md",
    );
    await writeFile(staleAgentPath, "stale\n", "utf8");

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code"],
    });

    await expect(readFile(staleAgentPath, "utf8")).rejects.toThrow();
  });

  it("compiles every supported harness when --harness is omitted", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-cli-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "compile", "--project-root", projectRoot],
      {
        cwd: path.resolve("."),
      },
    );

    const compiledLines = stdout
      .trim()
      .split("\n")
      .filter((line) => line.startsWith("Compiled harness bundle:"));
    expect(compiledLines).toHaveLength(4);
    expect(compiledLines).toEqual(
      expect.arrayContaining([
        `Compiled harness bundle: ${path.join(projectRoot, ".claude")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".codex")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".cursor")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".copilot")}`,
      ]),
    );
  });

  it("compiles only explicitly selected harnesses when -H is repeated and comma-separated", async () => {
    const projectRoot = await makeRuntimeDirectory("compile-cli-explicit");
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const { stdout } = await execFileAsync(
      "npx",
      [
        "tsx",
        "src/index.ts",
        "compile",
        "--project-root",
        projectRoot,
        "-H",
        "cursor,copilot-cli",
        "-H",
        "cursor",
      ],
      {
        cwd: path.resolve("."),
      },
    );

    const compiledLines = stdout
      .trim()
      .split("\n")
      .filter((line) => line.startsWith("Compiled harness bundle:"));
    expect(compiledLines).toEqual([
      `Compiled harness bundle: ${path.join(projectRoot, ".cursor")}`,
      `Compiled harness bundle: ${path.join(projectRoot, ".copilot")}`,
    ]);
    await expect(pathExists(path.join(projectRoot, ".cursor"))).resolves.toBe(
      true,
    );
    await expect(pathExists(path.join(projectRoot, ".copilot"))).resolves.toBe(
      true,
    );
    await expect(pathExists(path.join(projectRoot, ".claude"))).resolves.toBe(
      false,
    );
    await expect(pathExists(path.join(projectRoot, ".codex"))).resolves.toBe(
      false,
    );
  });

  it("keeps help on -h and uses -H for harness selection on compile", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "compile", "--help"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain(
      "Emit one or more harness bundles from the repository skill and agent sources.",
    );
    expect(stdout).toContain("-h, --help");
    expect(stdout).toContain("-H, --harness <name...>");
  });

  it("compiles every supported harness when --harness is omitted", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "cheese-flow-cli-"),
    );
    createdDirectories.push(projectRoot);
    await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
      recursive: true,
    });
    await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
      recursive: true,
    });

    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "compile", "--project-root", projectRoot],
      {
        cwd: path.resolve("."),
      },
    );

    const compiledLines = stdout
      .trim()
      .split("\n")
      .filter((line) => line.startsWith("Compiled harness bundle:"));
    expect(compiledLines).toHaveLength(4);
    expect(compiledLines).toEqual(
      expect.arrayContaining([
        `Compiled harness bundle: ${path.join(projectRoot, ".claude")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".codex")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".cursor")}`,
        `Compiled harness bundle: ${path.join(projectRoot, ".copilot")}`,
      ]),
    );
  });

  it("keeps help on -h and uses -H for harness selection on compile", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "compile", "--help"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain(
      "Emit one or more harness bundles from the repository skill and agent sources.",
    );
    expect(stdout).toContain("-h, --help");
    expect(stdout).toContain("-H, --harness <name...>");
    expect(stdout).toContain("Defaults to all supported harnesses.");
  });

  it("keeps help on -h and uses -H for harness selection on install", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "install", "--help"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain("-h, --help");
    expect(stdout).toContain("-H, --harness <name...>");
    expect(stdout).toContain("auto-detect.");
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
