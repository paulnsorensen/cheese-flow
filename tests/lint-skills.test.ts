import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  formatLintReport,
  hasErrors,
  lintSkillSource,
  lintSkillsDirectory,
} from "../src/lib/lint-skills.js";

const createdDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function createSkillsRoot(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "cheese-lint-"));
  createdDirectories.push(root);
  return root;
}

async function writeSkill(
  skillsRoot: string,
  directoryName: string,
  contents: string,
): Promise<void> {
  const directory = path.join(skillsRoot, directoryName);
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "SKILL.md"), contents, "utf8");
}

const validBody = "# Skill body\n\nUse this skill to do a thing.\n";

describe("lintSkillSource", () => {
  it("accepts a valid skill", () => {
    const issues = lintSkillSource({
      directoryName: "valid-skill",
      relativeFile: "valid-skill/SKILL.md",
      source: `---\nname: valid-skill\ndescription: Performs a clearly described action when the user asks for it.\n---\n${validBody}`,
    });
    expect(issues).toEqual([]);
  });

  it("flags name/directory mismatch as an error", () => {
    const issues = lintSkillSource({
      directoryName: "real-name",
      relativeFile: "real-name/SKILL.md",
      source: `---\nname: other-name\ndescription: Performs a clearly described action when the user asks for it.\n---\n${validBody}`,
    });
    const rules = issues.map((entry) => entry.rule);
    expect(rules).toContain("name-matches-directory");
    expect(
      issues.find((entry) => entry.rule === "name-matches-directory")?.severity,
    ).toBe("error");
  });

  it("flags invalid kebab-case names", () => {
    const issues = lintSkillSource({
      directoryName: "BadName",
      relativeFile: "BadName/SKILL.md",
      source: `---\nname: BadName\ndescription: Performs a clearly described action when the user asks for it.\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) => entry.rule.startsWith("frontmatter:name")),
    ).toBe(true);
  });

  it("flags missing description", () => {
    const issues = lintSkillSource({
      directoryName: "no-desc",
      relativeFile: "no-desc/SKILL.md",
      source: `---\nname: no-desc\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) => entry.rule.startsWith("frontmatter:description")),
    ).toBe(true);
  });

  it("warns when the description is too short", () => {
    const issues = lintSkillSource({
      directoryName: "short-desc",
      relativeFile: "short-desc/SKILL.md",
      source: `---\nname: short-desc\ndescription: Too short.\n---\n${validBody}`,
    });
    const warning = issues.find(
      (entry) => entry.rule === "description-too-short",
    );
    expect(warning?.severity).toBe("warning");
  });

  it("warns when the body exceeds the recommended line limit", () => {
    const longBody = `${"line\n".repeat(600)}`;
    const issues = lintSkillSource({
      directoryName: "long-body",
      relativeFile: "long-body/SKILL.md",
      source: `---\nname: long-body\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${longBody}`,
    });
    const warning = issues.find((entry) => entry.rule === "body-too-long");
    expect(warning?.severity).toBe("warning");
  });

  it("flags scalar frontmatter with the <frontmatter> path label", () => {
    const issues = lintSkillSource({
      directoryName: "scalar",
      relativeFile: "scalar/SKILL.md",
      source: `---\n42\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) => entry.rule === "frontmatter:<frontmatter>"),
    ).toBe(true);
  });

  it("returns a parse error when frontmatter markers are missing", () => {
    const issues = lintSkillSource({
      directoryName: "broken",
      relativeFile: "broken/SKILL.md",
      source: "no frontmatter here\n",
    });
    expect(issues).toHaveLength(1);
    expect(issues[0]?.rule).toBe("frontmatter-parse");
    expect(issues[0]?.severity).toBe("error");
  });

  it("flags compatibility strings exceeding 500 characters", () => {
    const issues = lintSkillSource({
      directoryName: "wide-compat",
      relativeFile: "wide-compat/SKILL.md",
      source: `---\nname: wide-compat\ndescription: A perfectly fine description that is long enough for discovery.\ncompatibility: ${"x".repeat(600)}\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) =>
        entry.rule.startsWith("frontmatter:compatibility"),
      ),
    ).toBe(true);
  });
});

describe("lintSkillsDirectory", () => {
  it("reports SKILL.md is required when missing", async () => {
    const skillsRoot = await createSkillsRoot();
    await mkdir(path.join(skillsRoot, "empty-skill"), { recursive: true });

    const report = await lintSkillsDirectory(skillsRoot);

    expect(report.scanned).toBe(1);
    expect(report.issues).toHaveLength(1);
    expect(report.issues[0]?.rule).toBe("skill-md-required");
    expect(hasErrors(report)).toBe(true);
  });

  it("reports skill-md-required when SKILL.md is unreadable", async () => {
    const skillsRoot = await createSkillsRoot();
    await mkdir(path.join(skillsRoot, "unreadable-skill", "SKILL.md"), {
      recursive: true,
    });

    const report = await lintSkillsDirectory(skillsRoot);

    expect(report.scanned).toBe(1);
    expect(report.issues).toHaveLength(1);
    expect(report.issues[0]?.rule).toBe("skill-md-required");
    expect(report.issues[0]?.message).toBe("SKILL.md could not be read.");
    expect(hasErrors(report)).toBe(true);
  });

  it("returns a clean report when all skills validate", async () => {
    const skillsRoot = await createSkillsRoot();
    await writeSkill(
      skillsRoot,
      "good-skill",
      `---\nname: good-skill\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
    );

    const report = await lintSkillsDirectory(skillsRoot);

    expect(report.scanned).toBe(1);
    expect(report.issues).toEqual([]);
    expect(hasErrors(report)).toBe(false);
  });

  it("formatLintReport reports a clean run when issues are empty", () => {
    const text = formatLintReport({ scanned: 1, issues: [] });
    expect(text).toContain("1 skill scanned");
    expect(text).toContain("No issues found.");
  });

  it("formatLintReport summarizes counts", () => {
    const text = formatLintReport({
      scanned: 2,
      issues: [
        {
          skill: "a",
          file: "a/SKILL.md",
          severity: "error",
          rule: "frontmatter:name",
          message: "bad",
        },
        {
          skill: "b",
          file: "b/SKILL.md",
          severity: "warning",
          rule: "body-too-long",
          message: "long",
        },
      ],
    });
    expect(text).toContain("2 skills scanned");
    expect(text).toContain("[ERROR]");
    expect(text).toContain("[WARN]");
    expect(text).toContain("1 error(s), 1 warning(s)");
  });
});
