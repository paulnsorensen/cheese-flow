import { afterEach, describe, expect, it, vi } from "vitest";
import { lintSkillSource } from "../src/lib/lint-skills.js";
import * as schemas from "../src/lib/schemas.js";
import { cleanupSkillRoots, validBody } from "./helpers/lint-helpers.js";

afterEach(cleanupSkillRoots);

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
    const nameFinding = issues.find(
      (entry) => entry.rule === "frontmatter:name",
    );
    expect(nameFinding?.severity).toBe("error");
    expect(nameFinding?.message).toContain("name");
  });

  it("flags missing description", () => {
    const issues = lintSkillSource({
      directoryName: "no-desc",
      relativeFile: "no-desc/SKILL.md",
      source: `---\nname: no-desc\n---\n${validBody}`,
    });
    const descFinding = issues.find((entry) =>
      entry.rule.startsWith("frontmatter:description"),
    );
    expect(descFinding?.severity).toBe("error");
    expect(descFinding?.rule).toBe("frontmatter:description");
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
    const compatFinding = issues.find((entry) =>
      entry.rule.startsWith("frontmatter:compatibility"),
    );
    expect(compatFinding?.severity).toBe("error");
    expect(compatFinding?.rule).toBe("frontmatter:compatibility");
  });

  it("warns when allowed-tools uses Claude Code permission-glob syntax", () => {
    const issues = lintSkillSource({
      directoryName: "claude-perms",
      relativeFile: "claude-perms/SKILL.md",
      source: `---\nname: claude-perms\ndescription: A perfectly fine description that is long enough for discovery.\nallowed-tools: Bash(git diff:*), Read\n---\n${validBody}`,
    });
    const finding = issues.find(
      (entry) => entry.rule === "allowed-tools-claude-permission-syntax",
    );
    expect(finding?.severity).toBe("warning");
    expect(finding?.message).toContain("Bash(git diff:*)");
  });

  it("warns when allowed-tools is an array using Claude permission-glob", () => {
    const issues = lintSkillSource({
      directoryName: "claude-perms-array",
      relativeFile: "claude-perms-array/SKILL.md",
      source: `---\nname: claude-perms-array\ndescription: A perfectly fine description that is long enough for discovery.\nallowed-tools:\n  - Bash(gh:*)\n  - Read\n---\n${validBody}`,
    });
    const finding = issues.find(
      (entry) => entry.rule === "allowed-tools-claude-permission-syntax",
    );
    expect(finding?.severity).toBe("warning");
    expect(finding?.message).toContain("Bash(gh:*)");
  });

  it("does not warn on bare tool names in allowed-tools", () => {
    const issues = lintSkillSource({
      directoryName: "bare-tools",
      relativeFile: "bare-tools/SKILL.md",
      source: `---\nname: bare-tools\ndescription: A perfectly fine description that is long enough for discovery.\nallowed-tools:\n  - read\n  - write\n  - bash\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) =>
        entry.rule.startsWith("allowed-tools-claude-permission-syntax"),
      ),
    ).toBe(false);
  });

  it("warns when body references Claude-only Agent(...) tool", () => {
    const issues = lintSkillSource({
      directoryName: "agent-call",
      relativeFile: "agent-call/SKILL.md",
      source: `---\nname: agent-call\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nUse Agent(subagent_type="foo") to spawn a sub-agent.\n`,
    });
    const finding = issues.find(
      (entry) => entry.rule === "body-claude-only-tool",
    );
    expect(finding?.severity).toBe("warning");
    expect(finding?.message).toContain("Agent");
  });

  it("warns when body references Claude-only Task(...) tool", () => {
    const issues = lintSkillSource({
      directoryName: "task-call",
      relativeFile: "task-call/SKILL.md",
      source: `---\nname: task-call\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nDispatch via Task(...)\n`,
    });
    const finding = issues.find(
      (entry) => entry.rule === "body-claude-only-tool",
    );
    expect(finding?.severity).toBe("warning");
    expect(finding?.message).toContain("Task");
  });

  it("warns when body references PascalCase hook event names", () => {
    const issues = lintSkillSource({
      directoryName: "pascal-hook",
      relativeFile: "pascal-hook/SKILL.md",
      source: `---\nname: pascal-hook\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nFires on SessionStart and PreToolUse events.\n`,
    });
    const findings = issues.filter(
      (entry) => entry.rule === "body-pascal-hook-event",
    );
    expect(findings).toHaveLength(2);
    expect(findings.every((f) => f.severity === "warning")).toBe(true);
  });

  it("does not flag camelCase hook event names in body", () => {
    const issues = lintSkillSource({
      directoryName: "camel-hook",
      relativeFile: "camel-hook/SKILL.md",
      source: `---\nname: camel-hook\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nFires on sessionStart and preToolUse events.\n`,
    });
    expect(
      issues.some((entry) => entry.rule === "body-pascal-hook-event"),
    ).toBe(false);
  });

  it("stringifies non-Error throws from parseSkillFrontmatter", () => {
    const spy = vi
      .spyOn(schemas, "parseSkillFrontmatter")
      .mockImplementationOnce(() => {
        const stringyDoom: unknown = "stringy doom";
        throw stringyDoom;
      });

    try {
      const issues = lintSkillSource({
        directoryName: "stringy",
        relativeFile: "stringy/SKILL.md",
        source: `---\nname: stringy\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
      });
      const finding = issues.find(
        (entry) => entry.rule === "frontmatter-parse",
      );
      expect(finding?.message).toBe("stringy doom");
    } finally {
      spy.mockRestore();
    }
  });

  it("ignores allowed-tools when it is neither string nor array", () => {
    // YAML that produces a number for allowed-tools — the portability check
    // must short-circuit to undefined and not crash.
    const issues = lintSkillSource({
      directoryName: "weird-tools",
      relativeFile: "weird-tools/SKILL.md",
      source: `---\nname: weird-tools\ndescription: A perfectly fine description that is long enough for discovery.\nallowed-tools: 42\n---\n${validBody}`,
    });
    expect(
      issues.some(
        (entry) => entry.rule === "allowed-tools-claude-permission-syntax",
      ),
    ).toBe(false);
  });

  it("converts a non-ZodError throw from parseSkillFrontmatter to frontmatter-parse", () => {
    const spy = vi
      .spyOn(schemas, "parseSkillFrontmatter")
      .mockImplementationOnce(() => {
        throw new Error("synthetic non-zod failure");
      });

    try {
      const issues = lintSkillSource({
        directoryName: "weird-throw",
        relativeFile: "weird-throw/SKILL.md",
        source: `---\nname: weird-throw\ndescription: A perfectly fine description that is long enough for discovery.\n---\n${validBody}`,
      });
      const finding = issues.find(
        (entry) => entry.rule === "frontmatter-parse",
      );
      expect(finding?.message).toContain("synthetic non-zod failure");
    } finally {
      spy.mockRestore();
    }
  });

  it("flags Claude-only frontmatter fields via adapter capabilities", () => {
    const issues = lintSkillSource({
      directoryName: "claude-only-fields",
      relativeFile: "claude-only-fields/SKILL.md",
      source: `---\nname: claude-only-fields\ndescription: A perfectly fine description that is long enough for discovery.\nmodel: opus\ncontext: fork\n---\n${validBody}`,
    });
    // context: fork and model each produce one frontmatter-portability warning.
    const portability = issues.filter(
      (entry) => entry.rule === "frontmatter-portability",
    );
    expect(portability).toHaveLength(2);
    expect(portability.every((entry) => entry.severity === "warning")).toBe(
      true,
    );
  });

  it("does not flag context: inline because it is the portable default", () => {
    const issues = lintSkillSource({
      directoryName: "inline-context",
      relativeFile: "inline-context/SKILL.md",
      source: `---\nname: inline-context\ndescription: A perfectly fine description that is long enough for discovery.\ncontext: inline\n---\n${validBody}`,
    });
    expect(
      issues.some((entry) => entry.rule === "frontmatter-portability"),
    ).toBe(false);
  });

  it("context: fork produces exactly one portability warning (no duplicate)", () => {
    const issues = lintSkillSource({
      directoryName: "fork-context",
      relativeFile: "fork-context/SKILL.md",
      source: `---\nname: fork-context\ndescription: A perfectly fine description that is long enough for discovery.\ncontext: fork\n---\n${validBody}`,
    });
    const portability = issues.filter(
      (entry) => entry.rule === "frontmatter-portability",
    );
    expect(portability).toHaveLength(1);
  });

  it("Stop in body emits body-harness-only-hook-event, not body-pascal-hook-event", () => {
    const issues = lintSkillSource({
      directoryName: "stop-hook",
      relativeFile: "stop-hook/SKILL.md",
      source: `---\nname: stop-hook\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nFires on Stop events.\n`,
    });
    const stopFinding = issues.find(
      (entry) => entry.rule === "body-harness-only-hook-event",
    );
    expect(stopFinding?.severity).toBe("warning");
    expect(stopFinding?.message).toContain("Stop");
    expect(
      issues.find((entry) => entry.rule === "body-pascal-hook-event"),
    ).toBeUndefined();
  });

  it("stop (camelCase) in body does not emit any hook warning", () => {
    const issues = lintSkillSource({
      directoryName: "stop-camel",
      relativeFile: "stop-camel/SKILL.md",
      source: `---\nname: stop-camel\ndescription: A perfectly fine description that is long enough for discovery.\n---\n# Body\nFires on stop events.\n`,
    });
    expect(
      issues.find(
        (entry) =>
          entry.rule === "body-harness-only-hook-event" ||
          entry.rule === "body-pascal-hook-event",
      ),
    ).toBeUndefined();
  });

  it("runs portability checks even when frontmatter validation fails", () => {
    // name is uppercase (fails kebab-case), but the body still contains an
    // Agent(...) reference and the frontmatter sets context: fork. Both
    // portability findings must surface alongside the Zod error.
    const issues = lintSkillSource({
      directoryName: "BadName",
      relativeFile: "BadName/SKILL.md",
      source: `---\nname: BadName\ndescription: A perfectly fine description that is long enough for discovery.\ncontext: fork\n---\n# Body\nUse Agent(...) for sub-agent dispatch.\n`,
    });
    const nameFinding = issues.find(
      (entry) => entry.rule === "frontmatter:name",
    );
    expect(nameFinding?.severity).toBe("error");

    const portabilityFinding = issues.find(
      (entry) => entry.rule === "frontmatter-portability",
    );
    expect(portabilityFinding?.severity).toBe("warning");

    const bodyFinding = issues.find(
      (entry) => entry.rule === "body-claude-only-tool",
    );
    expect(bodyFinding?.severity).toBe("warning");
    expect(bodyFinding?.message).toContain("Agent");
  });

  it("attaches an absolute SKILL.md line number to body findings", () => {
    const issues = lintSkillSource({
      directoryName: "agent-line",
      relativeFile: "agent-line/SKILL.md",
      source: `---\nname: agent-line\ndescription: A perfectly fine description that is long enough for discovery.\n---\nfirst body line\nsecond line uses Agent(...)\n`,
    });
    const finding = issues.find(
      (entry) => entry.rule === "body-claude-only-tool",
    );
    // Frontmatter spans SKILL.md lines 1-4 (`---`, name, description, `---`).
    // Body line 2 is the Agent(...) line, so absolute = 4 + 2 = 6.
    expect(finding?.line).toBe(6);
  });
});
