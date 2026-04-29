import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  formatLintReport,
  hasErrors,
  lintSkillsDirectory,
} from "../src/lib/lint-skills.js";
import {
  cleanupSkillRoots,
  createSkillsRoot,
  validBody,
  writeSkill,
} from "./helpers/lint-helpers.js";

afterEach(cleanupSkillRoots);

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

  it("reports skill-md-unreadable when SKILL.md exists but cannot be read", async () => {
    const skillsRoot = await createSkillsRoot();
    await mkdir(path.join(skillsRoot, "unreadable-skill", "SKILL.md"), {
      recursive: true,
    });

    const report = await lintSkillsDirectory(skillsRoot);

    expect(report.scanned).toBe(1);
    expect(report.issues).toHaveLength(1);
    expect(report.issues[0]?.rule).toBe("skill-md-unreadable");
    expect(report.issues[0]?.message).toContain("SKILL.md could not be read");
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

  it("runs compile-test against harness adapters with emitSurface", async () => {
    const skillsRoot = await createSkillsRoot();
    await writeSkill(
      skillsRoot,
      "good-skill",
      `---\nname: good-skill\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
    );

    const report = await lintSkillsDirectory(skillsRoot);

    expect(
      report.issues.find((entry) => entry.rule.startsWith("compile-")),
    ).toBeUndefined();
  });

  it("skips compile-test when source has errors", async () => {
    const skillsRoot = await createSkillsRoot();
    // Malformed YAML causes a frontmatter-parse source error. The early
    // return in lintSkillDirectory should prevent compile-test from running,
    // so only the source error is reported (not duplicate adapter failures).
    await writeSkill(
      skillsRoot,
      "bad-yaml",
      `---\nname: bad-yaml\ndescription: A perfectly fine description that is long enough for discovery.\nallowed-tools: { unclosed: brace\n---\n${validBody}`,
    );

    const report = await lintSkillsDirectory(skillsRoot);

    const errorFinding = report.issues.find(
      (entry) => entry.severity === "error",
    );
    expect(errorFinding?.severity).toBe("error");
    expect(
      report.issues.find((entry) => entry.rule.startsWith("compile-")),
    ).toBeUndefined();
  });

  it("returns no issues when source is clean and every adapter compiles", async () => {
    const skillsRoot = await createSkillsRoot();
    await writeSkill(
      skillsRoot,
      "good-skill",
      `---\nname: good-skill\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
    );
    const report = await lintSkillsDirectory(skillsRoot);
    expect(report.issues).toEqual([]);
  });

  it("formatLintReport reports a clean run when issues are empty", () => {
    const text = formatLintReport({ scanned: 1, issues: [] });
    expect(text).toContain("1 skill scanned");
    expect(text).toContain("No issues found.");
  });

  it("formatLintReport anchors body findings with file:line", () => {
    const text = formatLintReport({
      scanned: 1,
      issues: [
        {
          skill: "x",
          file: "x/SKILL.md",
          severity: "warning",
          rule: "body-claude-only-tool",
          message: "agent-only",
          line: 42,
        },
      ],
    });
    expect(text).toContain("x/SKILL.md:42");
  });

  it("converts compile-trip findings into LintIssues when source is clean", async () => {
    const skillsRoot = await createSkillsRoot();
    await writeSkill(
      skillsRoot,
      "clean-skill",
      `---\nname: clean-skill\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
    );

    const report = await lintSkillsDirectory(skillsRoot, {
      compile: async () => [
        {
          rule: "compile-cursor-failed",
          severity: "error",
          message: "synthetic adapter failure",
        },
        {
          rule: "compile-codex-warned",
          severity: "warning",
          message: "synthetic adapter warning at body line 3",
          line: 3,
        },
      ],
    });
    const compileIssue = report.issues.find(
      (entry) => entry.rule === "compile-cursor-failed",
    );
    expect(compileIssue?.severity).toBe("error");
    expect(compileIssue?.message).toContain("synthetic adapter failure");
    expect(compileIssue?.skill).toBe("clean-skill");
    expect(compileIssue?.line).toBeUndefined();

    const linedIssue = report.issues.find(
      (entry) => entry.rule === "compile-codex-warned",
    );
    expect(linedIssue?.line).toBe(3);
  });

  it("emits skill-md-unreadable when SKILL.md is a directory (EISDIR)", async () => {
    const skillsRoot = await createSkillsRoot();
    // Sibling skill with a regular SKILL.md — should produce no issues.
    const skillDir = path.join(skillsRoot, "blocked-skill");
    await mkdir(skillDir, { recursive: true });
    await writeFile(path.join(skillDir, "SKILL.md"), "ok\n", "utf8");
    // Force readFile(EISDIR) by making SKILL.md a directory. stat() succeeds
    // (it's a real entry), but readFile rejects with EISDIR — exercising the
    // non-ENOENT branch in the SKILL.md loader.
    const other = path.join(skillsRoot, "dir-as-file");
    await mkdir(path.join(other, "SKILL.md"), { recursive: true });

    const report = await lintSkillsDirectory(skillsRoot);
    const unreadableFinding = report.issues.find(
      (issue) => issue.rule === "skill-md-unreadable",
    );
    expect(unreadableFinding?.severity).toBe("error");
    expect(unreadableFinding?.skill).toBe("dir-as-file");
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
