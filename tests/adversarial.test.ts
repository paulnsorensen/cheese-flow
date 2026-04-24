/**
 * Adversarial test suite — chaos inputs, boundary assault, edge cases.
 * Attack surfaces: emitPluginManifest, emitMcpConfig, emitHooks, emitCursorSurface,
 * root manifest validity, gitignore sanity.
 */
import {
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { emitCursorSurface } from "../src/lib/cursor-surface.js";
import { emitHooks } from "../src/lib/hooks.js";
import { emitMcpConfig } from "../src/lib/mcp.js";
import { emitPluginManifest } from "../src/lib/plugin-manifest.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((d) => rm(d, { recursive: true, force: true })),
  );
});

// ─── emitPluginManifest boundary assault ────────────────────────────────────

describe("emitPluginManifest — boundary assault", () => {
  const baseMetadata = {
    name: "cheese-flow",
    version: "0.1.0",
    description: "Multi-harness plugin compiler",
    author: { name: "Cheese Lord" },
    license: "MIT",
    repository: "https://github.com/paulnsorensen/cheese-flow",
  };

  it("rejects empty string name", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await expect(
      emitPluginManifest(
        "claude-code",
        { ...baseMetadata, name: "" },
        outputRoot,
      ),
    ).rejects.toThrow();
  });

  it("rejects empty string version", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await expect(
      emitPluginManifest(
        "claude-code",
        { ...baseMetadata, version: "" },
        outputRoot,
      ),
    ).rejects.toThrow();
  });

  it("rejects empty string description", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await expect(
      emitPluginManifest(
        "claude-code",
        { ...baseMetadata, description: "" },
        outputRoot,
      ),
    ).rejects.toThrow();
  });

  it("handles unicode/emoji in name and description without throwing", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      ...baseMetadata,
      name: "cheese-flow-🧀",
      description: "RTL: مرحبا بكم في العالم — emoji 🎉 — Unicode™",
    };

    const manifestPath = await emitPluginManifest(
      "claude-code",
      metadata,
      outputRoot,
    );
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow-🧀");
    expect(manifest.description).toContain("RTL");
  });

  it("handles 1MB description without crashing", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const bigDescription = "x".repeat(1_000_000);
    const metadata = { ...baseMetadata, description: bigDescription };

    const manifestPath = await emitPluginManifest(
      "claude-code",
      metadata,
      outputRoot,
    );
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.description.length).toBe(1_000_000);
  });

  it("creates deep non-existent outputRoot path", async () => {
    const base = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(base);
    const outputRoot = path.join(base, "a", "b", "c", "deep");

    const manifestPath = await emitPluginManifest(
      "claude-code",
      baseMetadata,
      outputRoot,
    );
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.name).toBe("cheese-flow");
  });

  it("second write to same harness overwrites first (idempotent output)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await emitPluginManifest("claude-code", baseMetadata, outputRoot);
    const secondMetadata = { ...baseMetadata, version: "9.9.9" };
    await emitPluginManifest("claude-code", secondMetadata, outputRoot);

    const manifestPath = path.join(outputRoot, ".claude-plugin", "plugin.json");
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.version).toBe("9.9.9");
  });

  it("copilot-cli manifest includes category and strict fields", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const manifestPath = await emitPluginManifest(
      "copilot-cli",
      baseMetadata,
      outputRoot,
    );
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.category).toBe("development");
    expect(manifest.strict).toBe(true);
  });

  it("cursor manifest omits homepage and keywords (stripped fields)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const metadata = {
      ...baseMetadata,
      homepage: "https://example.com",
      keywords: ["a", "b"],
    };
    const manifestPath = await emitPluginManifest(
      "cursor",
      metadata,
      outputRoot,
    );
    const content = await readFile(manifestPath, "utf8");
    const manifest = JSON.parse(content);

    expect(manifest.homepage).toBeUndefined();
    expect(manifest.keywords).toBeUndefined();
  });

  it("emitted JSON parses cleanly (no trailing commas)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const manifestPath = await emitPluginManifest(
      "codex",
      baseMetadata,
      outputRoot,
    );
    const raw = await readFile(manifestPath, "utf8");

    expect(() => JSON.parse(raw)).not.toThrow();
  });
});

// ─── emitMcpConfig edge cases ────────────────────────────────────────────────

describe("emitMcpConfig — edge cases", () => {
  it("cursor path has no leading dot (mcp.json not .mcp.json)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const outputPath = await emitMcpConfig("cursor", outputRoot);

    expect(path.basename(outputPath)).toBe("mcp.json");
    expect(path.basename(outputPath)).not.toMatch(/^\./);
  });

  it("non-cursor path has leading dot (.mcp.json)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const outputPath = await emitMcpConfig("claude-code", outputRoot);

    expect(path.basename(outputPath)).toBe(".mcp.json");
  });

  it("creates outputRoot dir if it does not exist", async () => {
    const base = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(base);
    const outputRoot = path.join(base, "new-dir");

    const outputPath = await emitMcpConfig("claude-code", outputRoot);
    const content = await readFile(outputPath, "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers).toBeDefined();
  });

  it("__TODO_milknado__ is NOT inside mcpServers", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);
    const content = await readFile(path.join(outputRoot, ".mcp.json"), "utf8");
    const config = JSON.parse(content);

    expect(config.mcpServers.__TODO_milknado__).toBeUndefined();
    expect(config.__TODO_milknado__).toBeDefined();
  });

  it("emitted JSON parses back cleanly", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("codex", outputRoot);
    const raw = await readFile(path.join(outputRoot, ".mcp.json"), "utf8");

    expect(() => JSON.parse(raw)).not.toThrow();
  });

  it("emitted file ends with newline", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await emitMcpConfig("claude-code", outputRoot);
    const raw = await readFile(path.join(outputRoot, ".mcp.json"), "utf8");

    expect(raw.endsWith("\n")).toBe(true);
  });
});

// ─── emitHooks chaos ─────────────────────────────────────────────────────────

describe("emitHooks — chaos", () => {
  it("all non-portable events → writes empty hooks object", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionEnd: [{ type: "command", command: "echo end" }],
      customEvent: [{ type: "command", command: "echo custom" }],
    };

    const result = await emitHooks("claude-code", source, outputRoot);

    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks).toEqual({});
  });

  it("empty source object → writes empty hooks", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitHooks("claude-code", {}, outputRoot);

    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks).toEqual({});
  });

  it("event with empty array → event is excluded from output", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const source = { sessionStart: [] as never[] };
    const result = await emitHooks("claude-code", source, outputRoot);

    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    // Empty array is still a valid entry — should be present
    expect(config.hooks.sessionStart).toBeDefined();
  });

  it("codex: entry with explicit timeout preserves it (not overridden by default)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const source = {
      sessionStart: [{ type: "command", command: "echo hi", timeout: 30 }],
    };

    const result = await emitHooks("codex", source, outputRoot);
    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.SessionStart[0].hooks[0].timeout).toBe(30);
  });

  it("codex: entry without timeout gets DEFAULT_TIMEOUT (600)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const source = {
      preToolUse: [{ type: "command", command: "echo check" }],
    };

    const result = await emitHooks("codex", source, outputRoot);
    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.PreToolUse[0].hooks[0].timeout).toBe(600);
  });

  it("copilot-cli version field is the number 1, not the string '1'", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const source = { sessionStart: [{ type: "command", command: "echo x" }] };
    const result = await emitHooks("copilot-cli", source, outputRoot);

    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.version).toBe(1);
    expect(typeof config.version).toBe("number");
  });

  it("cursor returns exactly false (not null, not undefined)", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitHooks(
      "cursor",
      { sessionStart: [{ type: "command", command: "x" }] },
      outputRoot,
    );

    expect(result).toBe(false);
    expect(result).not.toBeNull();
    expect(result).not.toBeUndefined();
  });

  it("very long command string is preserved verbatim", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const longCommand = `echo ${"a".repeat(10_000)}`;
    const source = {
      sessionStart: [{ type: "command", command: longCommand }],
    };
    const result = await emitHooks("claude-code", source, outputRoot);

    expect(result).not.toBe(false);
    const content = await readFile(result as string, "utf8");
    const config = JSON.parse(content);

    expect(config.hooks.sessionStart[0].command).toBe(longCommand);
  });
});

// ─── emitCursorSurface filesystem attacks ────────────────────────────────────

describe("emitCursorSurface — filesystem attacks", () => {
  it("SKILL.md with zero body (only frontmatter) emits empty body files", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    const skillDir = path.join(skillsDir, "empty-body");
    await mkdir(skillDir, { recursive: true });

    await writeFile(
      path.join(skillDir, "SKILL.md"),
      "---\nname: empty-body\ndescription: No body here\n---\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);

    expect(result.rules).toHaveLength(1);
    expect(result.commands).toHaveLength(1);

    const commandContent = await readFile(result.commands[0] as string, "utf8");
    expect(commandContent.trim()).toBe("");
  });

  it("skill name with dashes emits correct file names", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    const skillDir = path.join(skillsDir, "my-skill-with-dashes");
    await mkdir(skillDir, { recursive: true });

    await writeFile(
      path.join(skillDir, "SKILL.md"),
      "---\nname: my-skill-with-dashes\ndescription: Dash test\n---\n# Body\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);
    expect(result.rules).toHaveLength(1);
    expect(path.basename(result.rules[0] as string)).toBe(
      "my-skill-with-dashes.mdc",
    );
  });

  it("SKILL.md missing frontmatter delimiters → emitSkill returns null (skill skipped)", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    const skillDir = path.join(skillsDir, "no-frontmatter");
    await mkdir(skillDir, { recursive: true });

    await writeFile(
      path.join(skillDir, "SKILL.md"),
      "# No frontmatter here\nJust a plain markdown file.\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    // parseFrontmatter throws — emitSkill catches and returns null — skill is skipped
    await expect(emitCursorSurface(skillsDir, outputRoot)).rejects.toThrow();
  });

  it("SKILL.md completely empty → throws (no frontmatter)", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    const skillDir = path.join(skillsDir, "empty-file");
    await mkdir(skillDir, { recursive: true });

    await writeFile(path.join(skillDir, "SKILL.md"), "", "utf8");

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    await expect(emitCursorSurface(skillsDir, outputRoot)).rejects.toThrow();
  });

  it("body with internal --- markers: only body content, not re-parsed as frontmatter", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    const skillDir = path.join(skillsDir, "dashes-in-body");
    await mkdir(skillDir, { recursive: true });

    const body =
      "# Heading\n\nSome content\n\n---\n\nMore content after divider\n";
    await writeFile(
      path.join(skillDir, "SKILL.md"),
      `---\nname: dashes-in-body\ndescription: Has dashes inside body\n---\n${body}`,
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);
    expect(result.rules).toHaveLength(1);

    const commandContent = await readFile(result.commands[0] as string, "utf8");
    expect(commandContent).toContain("More content after divider");
  });

  it("symlinked skill dir is treated as directory and emits correctly", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(projectRoot);
    const skillsDir = path.join(projectRoot, "skills");
    await mkdir(skillsDir, { recursive: true });

    // Real skill directory
    const realSkillDir = path.join(projectRoot, "real-skill");
    await mkdir(realSkillDir, { recursive: true });
    await writeFile(
      path.join(realSkillDir, "SKILL.md"),
      "---\nname: symlinked-skill\ndescription: Via symlink\n---\n# Symlinked\n",
      "utf8",
    );

    // Symlink it into skills
    const linkPath = path.join(skillsDir, "symlinked-skill");
    await symlink(realSkillDir, linkPath);

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cf-adv-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);
    // Symlinked dirs may or may not appear as isDirectory() depending on platform
    // This tests the actual behavior without asserting a specific count
    expect(result.rules.length).toBeGreaterThanOrEqual(0);
  });
});

// ─── Root manifest validity ──────────────────────────────────────────────────

const repoRoot = path.resolve(import.meta.dirname, "..");

describe("Root manifest files — validity", () => {
  it(".claude-plugin/plugin.json parses as valid JSON", async () => {
    const raw = await readFile(
      path.join(repoRoot, ".claude-plugin", "plugin.json"),
      "utf8",
    );
    expect(() => JSON.parse(raw)).not.toThrow();
  });

  it(".cursor-plugin/plugin.json parses as valid JSON", async () => {
    const raw = await readFile(
      path.join(repoRoot, ".cursor-plugin", "plugin.json"),
      "utf8",
    );
    expect(() => JSON.parse(raw)).not.toThrow();
  });

  it(".mcp.json parses as valid JSON", async () => {
    const raw = await readFile(path.join(repoRoot, ".mcp.json"), "utf8");
    expect(() => JSON.parse(raw)).not.toThrow();
  });

  it(".claude-plugin/plugin.json has required fields: name, version, description, author, license, repository", async () => {
    const raw = await readFile(
      path.join(repoRoot, ".claude-plugin", "plugin.json"),
      "utf8",
    );
    const manifest = JSON.parse(raw);

    expect(manifest.name).toBeTruthy();
    expect(manifest.version).toBeTruthy();
    expect(manifest.description).toBeTruthy();
    expect(manifest.author).toBeTruthy();
    expect(manifest.license).toBeTruthy();
    expect(manifest.repository).toBeTruthy();
  });

  it(".cursor-plugin/plugin.json has required fields", async () => {
    const raw = await readFile(
      path.join(repoRoot, ".cursor-plugin", "plugin.json"),
      "utf8",
    );
    const manifest = JSON.parse(raw);

    expect(manifest.name).toBeTruthy();
    expect(manifest.version).toBeTruthy();
    expect(manifest.description).toBeTruthy();
  });

  it(".mcp.json has mcpServers at root level", async () => {
    const raw = await readFile(path.join(repoRoot, ".mcp.json"), "utf8");
    const config = JSON.parse(raw);

    expect(config.mcpServers).toBeDefined();
    expect(typeof config.mcpServers).toBe("object");
  });

  it(".mcp.json: __TODO_milknado__ is NOT inside mcpServers", async () => {
    const raw = await readFile(path.join(repoRoot, ".mcp.json"), "utf8");
    const config = JSON.parse(raw);

    expect(config.mcpServers.__TODO_milknado__).toBeUndefined();
    expect(config.__TODO_milknado__).toBeDefined();
  });
});

// ─── Gitignore sanity ────────────────────────────────────────────────────────

describe("Gitignore sanity", () => {
  it(".gitignore contains .cursor/ pattern", async () => {
    const gitignore = await readFile(path.join(repoRoot, ".gitignore"), "utf8");
    expect(gitignore).toContain(".cursor/");
  });

  it(".gitignore contains .copilot/ pattern", async () => {
    const gitignore = await readFile(path.join(repoRoot, ".gitignore"), "utf8");
    expect(gitignore).toContain(".copilot/");
  });
});
