import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
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
  agentFrontmatterSchema,
  resolveModel,
  skillFrontmatterSchema,
} from "../src/lib/schemas.js";

const createdDirectories: string[] = [];
const execFileAsync = promisify(execFile);

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await import("node:fs/promises").then(({ rm }) =>
        rm(directory, { recursive: true, force: true }),
      );
    }),
  );
});

describe("installHarnessArtifacts", () => {
  it("compiles the basic agent template for Claude Code and Codex", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);
    await import("node:fs/promises").then(async ({ cp }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
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
    await import("node:fs/promises").then(async ({ mkdir, cp }) => {
      await mkdir(path.join(projectRoot, "agents"), { recursive: true });
      await mkdir(path.join(projectRoot, "skills", "wrong-name"), {
        recursive: true,
      });
      await cp(
        path.resolve("agents", "basic-agent.md.eta"),
        path.join(projectRoot, "agents", "basic-agent.md.eta"),
      );
    });

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
    await import("node:fs/promises").then(async ({ cp, mkdir }) => {
      await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
        recursive: true,
      });
      await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
        recursive: true,
      });
      await mkdir(path.join(projectRoot, "skills", "nested-dir"), {
        recursive: true,
      });
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

    expect(manifest.agents).toEqual(["basic-agent.md"]);
    expect(manifest.skills).toEqual(["basic-skill", "nested-dir"]);
    expect(manifest.commands).toEqual([]);
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
    const skill = skillFrontmatterSchema.parse({
      name: "basic-skill",
      description: "Portable skill",
      "allowed-tools": "read write",
    });
    const agent = agentFrontmatterSchema.parse({
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
