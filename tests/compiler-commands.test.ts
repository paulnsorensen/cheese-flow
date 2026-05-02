import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { compileHarnessBundles } from "../src/lib/compiler.js";
import { parseCommandFrontmatter } from "../src/lib/schemas.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function makeProjectRoot(prefix: string): Promise<string> {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), prefix));
  createdDirectories.push(projectRoot);
  return projectRoot;
}

async function seedAgentsAndSkills(projectRoot: string): Promise<void> {
  await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
    recursive: true,
  });
  await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
    recursive: true,
  });
}

async function readManifest(
  projectRoot: string,
  outputRoot: string,
): Promise<{ commands: string[] }> {
  return JSON.parse(
    await readFile(path.join(projectRoot, outputRoot, "manifest.json"), "utf8"),
  ) as { commands: string[] };
}

describe("compileHarnessBundles command output", () => {
  it("copies command files and lists them in the manifest for both harnesses", async () => {
    const projectRoot = await makeProjectRoot("cheese-flow-commands-");
    await seedAgentsAndSkills(projectRoot);
    await mkdir(path.join(projectRoot, "commands"), { recursive: true });
    await writeFile(
      path.join(projectRoot, "commands", "alpha.md"),
      `---\nname: alpha\ndescription: First portable command.\nargument-hint: "<input>"\n---\n# Alpha\n`,
      "utf8",
    );
    await writeFile(
      path.join(projectRoot, "commands", "beta.md"),
      `---\nname: beta\ndescription: Second portable command.\n---\n# Beta\n`,
      "utf8",
    );
    await writeFile(
      path.join(projectRoot, "commands", "notes.txt"),
      "ignore me\n",
      "utf8",
    );

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code", "codex"],
    });

    for (const root of [".claude", ".codex"]) {
      const manifest = await readManifest(projectRoot, root);
      expect(manifest.commands).toEqual(["alpha.md", "beta.md"]);
      const copied = await readFile(
        path.join(projectRoot, root, "commands", "alpha.md"),
        "utf8",
      );
      expect(copied).toContain("name: alpha");
      expect(copied).toContain("# Alpha");
    }
  });

  it("propagates non-ENOENT readdir errors from the commands directory", async () => {
    const projectRoot = await makeProjectRoot("cheese-flow-commands-notdir-");
    await seedAgentsAndSkills(projectRoot);
    await writeFile(
      path.join(projectRoot, "commands"),
      "this is a file, not a directory",
      "utf8",
    );

    await expect(
      compileHarnessBundles({ projectRoot, harnesses: ["claude-code"] }),
    ).rejects.toThrow();
  });

  it("rejects commands whose filename does not match the frontmatter name", async () => {
    const projectRoot = await makeProjectRoot("cheese-flow-command-mismatch-");
    await seedAgentsAndSkills(projectRoot);
    await mkdir(path.join(projectRoot, "commands"), { recursive: true });
    await writeFile(
      path.join(projectRoot, "commands", "wrong-name.md"),
      `---\nname: right-name\ndescription: Mismatched command file.\n---\n# Wrong\n`,
      "utf8",
    );

    await expect(
      compileHarnessBundles({ projectRoot, harnesses: ["claude-code"] }),
    ).rejects.toThrow(/must match frontmatter name/u);
  });

  it("validates the command frontmatter contract", () => {
    const command = parseCommandFrontmatter({
      name: "cheese",
      description: "Top-level router command.",
      "argument-hint": "<input>",
    });

    expect(command.name).toBe("cheese");
    expect(command["argument-hint"]).toBe("<input>");
  });
});

describe("shipped command scaffolds", () => {
  it("copies all six scaffolded top-level commands into each harness", async () => {
    const projectRoot = await makeProjectRoot("cheese-flow-shipped-commands-");
    await seedAgentsAndSkills(projectRoot);
    await cp(path.resolve("commands"), path.join(projectRoot, "commands"), {
      recursive: true,
    });

    await compileHarnessBundles({
      projectRoot,
      harnesses: ["claude-code", "codex"],
    });

    const expected = [
      "age.md",
      "briesearch.md",
      "cheese.md",
      "cook.md",
      "culture.md",
      "mold.md",
      "nih-audit.md",
    ];
    for (const root of [".claude", ".codex"]) {
      const manifest = await readManifest(projectRoot, root);
      expect([...manifest.commands].sort()).toEqual(expected);
    }
  });
});
