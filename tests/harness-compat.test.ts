import { describe, expect, it } from "vitest";
import {
  checkAllowedToolsPortability,
  checkBodyHarnessIdioms,
  compileTestSkill,
} from "../src/lib/harness-compat.js";

describe("checkAllowedToolsPortability", () => {
  it("returns no findings when allowed-tools is undefined", () => {
    expect(checkAllowedToolsPortability(undefined)).toEqual([]);
  });

  it("returns no findings on bare tool names (string form)", () => {
    expect(checkAllowedToolsPortability("read write bash")).toEqual([]);
  });

  it("returns no findings on bare tool names (array form)", () => {
    expect(checkAllowedToolsPortability(["read", "write", "bash"])).toEqual([]);
  });

  it("flags Claude permission-glob in string form", () => {
    const findings = checkAllowedToolsPortability("Bash(git diff:*), Read");
    expect(findings).toHaveLength(1);
    expect(findings[0]?.rule).toBe("allowed-tools-claude-permission-syntax");
    expect(findings[0]?.severity).toBe("warning");
  });

  it("flags Claude permission-glob in array form", () => {
    const findings = checkAllowedToolsPortability([
      "Bash(gh:*)",
      "mcp__tilth__tilth_search",
    ]);
    expect(findings).toHaveLength(1);
    expect(findings[0]?.message).toContain("Bash(gh:*)");
  });

  it("flags all occurrences when multiple permission-globs are present", () => {
    const findings = checkAllowedToolsPortability("Bash(git:*), Bash(gh:*)");
    expect(findings).toHaveLength(2);
    expect(findings[0]?.message).toContain("Bash(git:*)");
    expect(findings[1]?.message).toContain("Bash(gh:*)");
  });

  it("flags lowercase permission-glob syntax", () => {
    const findings = checkAllowedToolsPortability("bash(git diff:*)");
    expect(findings).toHaveLength(1);
    expect(findings[0]?.rule).toBe("allowed-tools-claude-permission-syntax");
  });
});

describe("checkBodyHarnessIdioms", () => {
  it("returns no findings on plain markdown body", () => {
    const body = "# Heading\n\nUse the harness's native tools.\n";
    expect(checkBodyHarnessIdioms(body)).toEqual([]);
  });

  it("flags Agent(...) call sites", () => {
    const findings = checkBodyHarnessIdioms('Use Agent(subagent_type="x")');
    expect(findings).toHaveLength(1);
    expect(findings[0]?.rule).toBe("body-claude-only-tool");
  });

  it("flags Task(...) call sites", () => {
    const findings = checkBodyHarnessIdioms("Spawn via Task(...).");
    expect(findings).toHaveLength(1);
    expect(findings[0]?.message).toContain("Task");
  });

  it("flags multiple PascalCase hook events", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires SessionStart, PreToolUse, PostToolUse.",
    );
    expect(
      findings.filter((f) => f.rule === "body-pascal-hook-event"),
    ).toHaveLength(3);
  });

  it("does not flag camelCase hook events", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires sessionStart, preToolUse, postToolUse.",
    );
    expect(findings).toEqual([]);
  });
});

describe("compileTestSkill", () => {
  const validSkill =
    "---\nname: my-skill\ndescription: A long-enough description for portable discovery.\n---\n# Body\nDo something useful.\n";

  it("returns no findings for a valid skill", async () => {
    const findings = await compileTestSkill("my-skill", validSkill);
    expect(findings).toEqual([]);
  });

  it("reports a compile failure when frontmatter is malformed", async () => {
    const malformed = "no frontmatter at all\n";
    const findings = await compileTestSkill("broken-skill", malformed);
    expect(findings.length).toBeGreaterThan(0);
    expect(findings.every((f) => f.severity === "error")).toBe(true);
    expect(findings.some((f) => f.rule.startsWith("compile-cursor-"))).toBe(
      true,
    );
  });
});
