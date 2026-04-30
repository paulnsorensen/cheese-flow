import { describe, expect, it } from "vitest";
import { harnessAdapters } from "../src/adapters/index.js";
import type { HarnessAdapter } from "../src/domain/harness.js";
import { fieldSupport } from "../src/lib/capabilities.js";
import {
  checkAllowedToolsPortability,
  checkBodyHarnessIdioms,
  checkFrontmatterPortability,
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
    expect(findings[0]?.rule).toBe("allowed-tools-claude-permission-syntax");
    expect(findings[0]?.severity).toBe("warning");
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
    expect(findings[0]?.severity).toBe("warning");
    expect(findings[0]?.message).toContain("bash(git diff:*)");
  });
});

describe("checkFrontmatterPortability", () => {
  it("returns no findings for skills using only portable fields", () => {
    expect(
      checkFrontmatterPortability({ name: "x", description: "y" }, "skill"),
    ).toEqual([]);
  });

  it("flags model and context: fork on a skill (2 findings)", () => {
    const findings = checkFrontmatterPortability(
      { name: "x", description: "y", model: "opus", context: "fork" },
      "skill",
    );
    expect(findings).toHaveLength(2);
    expect(findings.every((f) => f.rule === "frontmatter-portability")).toBe(
      true,
    );
    expect(findings.some((f) => f.message.includes('"model"'))).toBe(true);
    expect(findings.some((f) => f.message.includes('"context"'))).toBe(true);
  });

  it("does not flag context: inline because it is the portable default", () => {
    const findings = checkFrontmatterPortability(
      { name: "x", description: "y", context: "inline" },
      "skill",
    );
    expect(findings).toEqual([]);
  });

  it("flags all Claude-only agent fields", () => {
    const findings = checkFrontmatterPortability(
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
    expect(findings.every((f) => f.rule === "frontmatter-portability")).toBe(
      true,
    );
  });

  it("is driven by adapter capabilities, not hardcoded constants", () => {
    // model is supported only by claude-code; if a future adapter also declares it,
    // the map grows and the warning would no longer fire for that adapter.
    // Verify the current mapping is capability-driven.
    const support = fieldSupport("skill");
    expect(support.get("model")).toEqual(["claude-code"]);
    expect(support.get("context")).toEqual(["claude-code"]);
  });

  it("warning suppresses when every adapter (including a hypothetical fifth) declares the field", () => {
    // Plan §6 regression: prove the lint is data-driven by mutating the registry
    // so every adapter declares `model` in skillFrontmatterKeys. The warning
    // must stop firing — adding a portable field means editing capabilities,
    // not the lint.
    const skillsBefore = checkFrontmatterPortability(
      { name: "x", description: "y", model: "opus" },
      "skill",
    );
    expect(skillsBefore).toHaveLength(1);

    const registry = harnessAdapters as Record<string, HarnessAdapter>;
    const original = new Map<string, ReadonlySet<string>>();
    for (const [name, adapter] of Object.entries(registry)) {
      original.set(name, adapter.capabilities.skillFrontmatterKeys);
      adapter.capabilities = {
        ...adapter.capabilities,
        skillFrontmatterKeys: new Set([
          ...adapter.capabilities.skillFrontmatterKeys,
          "model",
        ]),
      };
    }
    const fifth = {
      ...(registry["claude-code"] as HarnessAdapter),
      displayName: "Fifth",
      outputRoot: ".fifth",
      capabilities: {
        skillFrontmatterKeys: new Set(["model"]),
        agentFrontmatterKeys: new Set<string>(),
        hookEvents: new Set<string>(),
        toolNames: new Set<string>(),
        bootstrapHook: false,
      },
    } as HarnessAdapter;
    registry["fifth"] = fifth;

    try {
      const skillsAfter = checkFrontmatterPortability(
        { name: "x", description: "y", model: "opus" },
        "skill",
      );
      expect(skillsAfter).toEqual([]);
    } finally {
      delete registry["fifth"];
      for (const [name, adapter] of Object.entries(registry)) {
        const restored = original.get(name);
        if (restored !== undefined) {
          adapter.capabilities = {
            ...adapter.capabilities,
            skillFrontmatterKeys: restored,
          };
        }
      }
    }
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

  it("flags portable PascalCase hook events with body-pascal-hook-event", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires SessionStart, PreToolUse, PostToolUse.",
    );
    expect(
      findings.filter((f) => f.rule === "body-pascal-hook-event"),
    ).toHaveLength(3);
  });

  it("flags claude-only PascalCase hook events with body-harness-only-hook-event", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires Stop, SubagentStop, Notification.",
    );
    expect(
      findings.filter((f) => f.rule === "body-harness-only-hook-event"),
    ).toHaveLength(3);
    expect(findings.every((f) => f.severity === "warning")).toBe(true);
  });

  it("Stop emits body-harness-only-hook-event, not body-pascal-hook-event", () => {
    const findings = checkBodyHarnessIdioms("Triggers on Stop.");
    const stopFinding = findings.find((f) => f.message.includes("Stop"));
    expect(stopFinding?.rule).toBe("body-harness-only-hook-event");
  });

  it("does not flag camelCase hook events", () => {
    const findings = checkBodyHarnessIdioms(
      "Fires sessionStart, preToolUse, postToolUse.",
    );
    expect(findings).toEqual([]);
  });

  it("does not flag camelCase stop in body", () => {
    const findings = checkBodyHarnessIdioms("Fires stop, subagentStop events.");
    expect(
      findings.some(
        (f) =>
          f.rule === "body-pascal-hook-event" ||
          f.rule === "body-harness-only-hook-event",
      ),
    ).toBe(false);
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
    expect(findings).toHaveLength(4);
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
