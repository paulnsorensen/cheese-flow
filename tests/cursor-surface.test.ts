import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cursorAdapter } from "../src/adapters/cursor.js";

const emitCursorSurface = (skillsDir: string, outputRoot: string) => {
  if (cursorAdapter.emitSurface === undefined) {
    throw new Error("cursorAdapter.emitSurface is undefined");
  }
  return cursorAdapter.emitSurface(skillsDir, outputRoot);
};

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories.splice(0).map(async (directory) => {
      await rm(directory, { recursive: true, force: true });
    }),
  );
});

describe("emitCursorSurface", () => {
  it("emits both .mdc rule and .md command for a skill", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const fooSkillDir = path.join(skillsDir, "foo");
    await mkdir(fooSkillDir, { recursive: true });

    await writeFile(
      path.join(fooSkillDir, "SKILL.md"),
      "---\nname: foo\ndescription: A test skill\n---\n# Foo Skill\n\nThis is a test.\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const rulePath = path.join(outputRoot, "rules", "foo.mdc");
    const commandPath = path.join(outputRoot, "commands", "foo.md");

    const ruleContent = await readFile(rulePath, "utf8");
    const commandContent = await readFile(commandPath, "utf8");

    expect(ruleContent).toContain("---");
    expect(commandContent).not.toContain("---");
  });

  it(".mdc rule has description and alwaysApply frontmatter", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const testSkillDir = path.join(skillsDir, "test-skill");
    await mkdir(testSkillDir, { recursive: true });

    await writeFile(
      path.join(testSkillDir, "SKILL.md"),
      "---\nname: test-skill\ndescription: Test description\n---\n# Body\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const rulePath = path.join(outputRoot, "rules", "test-skill.mdc");
    const ruleContent = await readFile(rulePath, "utf8");

    expect(ruleContent).toContain("description:");
    expect(ruleContent).toContain("alwaysApply: false");
  });

  it("command file has no frontmatter", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const cmdSkillDir = path.join(skillsDir, "cmd-skill");
    await mkdir(cmdSkillDir, { recursive: true });

    await writeFile(
      path.join(cmdSkillDir, "SKILL.md"),
      "---\nname: cmd-skill\ndescription: Command test\n---\n# Body Content\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const commandPath = path.join(outputRoot, "commands", "cmd-skill.md");
    const commandContent = await readFile(commandPath, "utf8");

    const firstLine = commandContent.split("\n")[0];
    expect(firstLine).not.toBe("---");
  });

  it("both rule and command contain body content", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const contentSkillDir = path.join(skillsDir, "content-skill");
    await mkdir(contentSkillDir, { recursive: true });

    const bodyContent = "# Test Body\n\nSome content here.";
    await writeFile(
      path.join(contentSkillDir, "SKILL.md"),
      `---\nname: content-skill\ndescription: Content test\n---\n${bodyContent}\n`,
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const rulePath = path.join(outputRoot, "rules", "content-skill.mdc");
    const commandPath = path.join(outputRoot, "commands", "content-skill.md");

    const ruleContent = await readFile(rulePath, "utf8");
    const commandContent = await readFile(commandPath, "utf8");

    expect(ruleContent).toContain("# Test Body");
    expect(commandContent).toContain("# Test Body");
  });

  it("emits all skills when multiple exist", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const skill1Dir = path.join(skillsDir, "skill-one");
    const skill2Dir = path.join(skillsDir, "skill-two");

    await mkdir(skill1Dir, { recursive: true });
    await mkdir(skill2Dir, { recursive: true });

    await writeFile(
      path.join(skill1Dir, "SKILL.md"),
      "---\nname: skill-one\ndescription: First skill\n---\n# One\n",
      "utf8",
    );
    await writeFile(
      path.join(skill2Dir, "SKILL.md"),
      "---\nname: skill-two\ndescription: Second skill\n---\n# Two\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const rule1 = await readFile(
      path.join(outputRoot, "rules", "skill-one.mdc"),
      "utf8",
    );
    const rule2 = await readFile(
      path.join(outputRoot, "rules", "skill-two.mdc"),
      "utf8",
    );
    const cmd1 = await readFile(
      path.join(outputRoot, "commands", "skill-one.md"),
      "utf8",
    );
    const cmd2 = await readFile(
      path.join(outputRoot, "commands", "skill-two.md"),
      "utf8",
    );

    expect(rule1).toContain("First skill");
    expect(rule2).toContain("Second skill");
    expect(cmd1).toContain("# One");
    expect(cmd2).toContain("# Two");
  });

  it("returns empty result when skillsDir does not exist", async () => {
    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface("/does/not/exist", outputRoot);

    expect(result).toEqual({ rules: [], commands: [] });
  });

  it("skips subdirectory without SKILL.md", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const emptyDir = path.join(skillsDir, "no-skill-md");
    await mkdir(emptyDir, { recursive: true });

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);

    expect(result).toEqual({ rules: [], commands: [] });
  });

  it("skips non-directory entries in skillsDir", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    await mkdir(skillsDir, { recursive: true });
    // Write a file (not directory) inside skillsDir
    await writeFile(
      path.join(skillsDir, "not-a-dir.md"),
      "# ignored\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    const result = await emitCursorSurface(skillsDir, outputRoot);

    expect(result).toEqual({ rules: [], commands: [] });
  });

  it("uses empty description when SKILL.md has no description field", async () => {
    const projectRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(projectRoot);

    const skillsDir = path.join(projectRoot, "skills");
    const noDescDir = path.join(skillsDir, "no-desc");
    await mkdir(noDescDir, { recursive: true });

    await writeFile(
      path.join(noDescDir, "SKILL.md"),
      "---\nname: no-desc\n---\n# Body only\n",
      "utf8",
    );

    const outputRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-"));
    createdDirectories.push(outputRoot);

    await emitCursorSurface(skillsDir, outputRoot);

    const rulePath = path.join(outputRoot, "rules", "no-desc.mdc");
    const ruleContent = await readFile(rulePath, "utf8");

    expect(ruleContent).toContain("description: \n");
    expect(ruleContent).toContain("# Body only");
  });
});
