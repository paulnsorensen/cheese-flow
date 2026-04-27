import { describe, expect, it } from "vitest";
import {
  checkAllowedToolsPortability,
  checkBodyHarnessIdioms,
  checkClaudeOnlyFields,
  checkContextPortability,
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

  it("flags multiple PascalCase hook events including the extended set", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires SessionStart, PreToolUse, PostToolUse, Stop, SubagentStop, Notification.",
    );
    expect(
      findings.filter((f) => f.rule === "body-pascal-hook-event"),
    ).toHaveLength(6);
  });

  it("does not flag camelCase hook events", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires sessionStart, preToolUse, postToolUse.",
    );
    expect(findings).toEqual([]);
  });

  it("flags Claude-only tools beyond Agent/Task", () => {
    const findings = checkBodyHarnessIdioms(
      "Use NotebookEdit(...) and WebSearch(...) and TodoWrite(...) and WebFetch(...).",
    );
    const tools = findings
      .filter((f) => f.rule === "body-claude-only-tool")
      .map((f) => f.message);
    expect(tools.some((m) => m.includes("NotebookEdit"))).toBe(true);
    expect(tools.some((m) => m.includes("WebSearch"))).toBe(true);
    expect(tools.some((m) => m.includes("TodoWrite"))).toBe(true);
    expect(tools.some((m) => m.includes("WebFetch"))).toBe(true);
  });

  it("flags harness-specific path markers", () => {
    const findings = checkBodyHarnessIdioms(
      "See .claude/specs and .codex/agents and .cursor/rules and AGENTS.md.",
    );
    const markers = findings
      .filter((f) => f.rule === "body-harness-path-marker")
      .map((f) => f.message);
    expect(markers.some((m) => m.includes(".claude/"))).toBe(true);
    expect(markers.some((m) => m.includes(".codex/"))).toBe(true);
    expect(markers.some((m) => m.includes(".cursor/"))).toBe(true);
    expect(markers.some((m) => m.includes("AGENTS.md"))).toBe(true);
  });

  it("attaches a 1-based line number to each body finding", () => {
    const body = "line 1\nline 2 with Agent(\nline 3\n";
    const findings = checkBodyHarnessIdioms(body);
    const agentFinding = findings.find(
      (f) => f.rule === "body-claude-only-tool",
    );
    expect(agentFinding?.line).toBe(2);
  });
});

describe("checkClaudeOnlyFields", () => {
  it("returns no findings for skills using only portable fields", () => {
    expect(
      checkClaudeOnlyFields({ name: "x", description: "y" }, "skill"),
    ).toEqual([]);
  });

  it("flags model and context: fork on a skill", () => {
    const findings = checkClaudeOnlyFields(
      { name: "x", description: "y", model: "opus", context: "fork" },
      "skill",
    );
    expect(findings).toHaveLength(2);
    expect(
      findings.every((f) => f.rule === "frontmatter-claude-only-field"),
    ).toBe(true);
  });

  it("does not flag context: inline because it is the portable default", () => {
    const findings = checkClaudeOnlyFields(
      { name: "x", description: "y", context: "inline" },
      "skill",
    );
    expect(findings).toEqual([]);
  });

  it("flags Claude-only agent fields", () => {
    const findings = checkClaudeOnlyFields(
      {
        name: "x",
        description: "y",
        skills: ["foo"],
        color: "red",
        effort: "high",
        disallowedTools: ["Edit"],
        permissionMode: "default",
      },
      "agent",
    );
    expect(findings).toHaveLength(5);
    expect(
      findings.every((f) => f.rule === "frontmatter-claude-only-field"),
    ).toBe(true);
  });
});

describe("checkContextPortability", () => {
  it("returns no findings when context is undefined", () => {
    expect(checkContextPortability(undefined)).toEqual([]);
  });

  it("returns no findings on context: inline", () => {
    expect(checkContextPortability("inline")).toEqual([]);
  });

  it("flags context: fork as Claude-only", () => {
    const findings = checkContextPortability("fork");
    expect(findings).toHaveLength(1);
    expect(findings[0]?.rule).toBe("context-fork-claude-only");
    expect(findings[0]?.severity).toBe("warning");
    expect(findings[0]?.message).toContain("forked subagent");
  });
});

describe("compileTestSkill", () => {
  const validSkill =
    "---\nname: my-skill\ndescription: A long-enough description for portable discovery.\n---\n# Body\nDo something useful.\n";

  it("returns no findings for a valid skill", async () => {
    const findings = await compileTestSkill("my-skill", validSkill);
    expect(findings).toEqual([]);
  });

  it("reports a compile failure for every adapter when frontmatter is malformed", async () => {
    const malformed = "no frontmatter at all\n";
    const findings = await compileTestSkill("broken-skill", malformed);
    expect(findings.length).toBeGreaterThan(0);
    expect(findings.every((f) => f.severity === "error")).toBe(true);
    const rules = findings.map((f) => f.rule);
    for (const harness of ["claude-code", "codex", "cursor", "copilot-cli"]) {
      expect(rules).toContain(`compile-${harness}-failed`);
    }
  });

  it("surfaces the directory-name mismatch as an adapter-level compile error", async () => {
    const mismatched =
      "---\nname: not-the-folder\ndescription: A long-enough description for portable discovery.\n---\n# Body\nSomething useful.\n";
    const findings = await compileTestSkill("expected-folder", mismatched);
    expect(
      findings.some((f) => f.message.includes("must match frontmatter name")),
    ).toBe(true);
  });
});
