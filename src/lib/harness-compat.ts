import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { harnessAdapters } from "../adapters/index.js";

export type HarnessCompatFinding = {
  rule: string;
  severity: "error" | "warning";
  message: string;
};

const CLAUDE_PERMISSION_GLOB = /\b([A-Za-z]\w*)\(([^)]*:[^)]*)\)/u;
const CLAUDE_ONLY_TOOL_NAMES = ["Agent", "Task"] as const;
const PASCAL_HOOK_EVENTS = [
  "SessionStart",
  "PreToolUse",
  "PostToolUse",
] as const;

export function checkAllowedToolsPortability(
  allowedTools: string | string[] | undefined,
): HarnessCompatFinding[] {
  if (allowedTools === undefined) return [];
  const text = Array.isArray(allowedTools)
    ? allowedTools.join(", ")
    : allowedTools;
  const matches = Array.from(
    text.matchAll(new RegExp(CLAUDE_PERMISSION_GLOB.source, "gu")),
  );
  if (matches.length === 0) return [];
  return matches.map((match) => ({
    rule: "allowed-tools-claude-permission-syntax",
    severity: "warning",
    message: `allowed-tools entry "${match[0]}" uses Claude Code permission-glob syntax; Cursor, Codex, and Copilot CLI do not parse it. Drop the "(...:...)" suffix or list bare tool names for portability.`,
  }));
}

export function checkBodyHarnessIdioms(body: string): HarnessCompatFinding[] {
  const findings: HarnessCompatFinding[] = [];
  for (const tool of CLAUDE_ONLY_TOOL_NAMES) {
    if (new RegExp(`\\b${tool}\\(`, "u").test(body)) {
      findings.push({
        rule: "body-claude-only-tool",
        severity: "warning",
        message: `body references Claude-only tool "${tool}(...)"; non-Claude harnesses do not expose this tool. Rephrase generically (e.g. "spawn a sub-agent").`,
      });
    }
  }
  for (const event of PASCAL_HOOK_EVENTS) {
    const camel = `${event.charAt(0).toLowerCase()}${event.slice(1)}`;
    if (new RegExp(`\\b${event}\\b`, "u").test(body)) {
      findings.push({
        rule: "body-pascal-hook-event",
        severity: "warning",
        message: `body references PascalCase hook event "${event}"; cheese-flow's portable hooks use camelCase ("${camel}"). Per-harness mapping is applied at compile time.`,
      });
    }
  }
  return findings;
}

export async function compileTestSkill(
  skillName: string,
  skillSource: string,
): Promise<HarnessCompatFinding[]> {
  const findings: HarnessCompatFinding[] = [];
  const tmpRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-compile-"));
  try {
    const skillsDir = path.join(tmpRoot, "skills");
    await mkdir(path.join(skillsDir, skillName), { recursive: true });
    await writeFile(
      path.join(skillsDir, skillName, "SKILL.md"),
      skillSource,
      "utf8",
    );

    for (const adapter of Object.values(harnessAdapters)) {
      if (adapter.emitSurface === undefined) continue;
      const outputRoot = path.join(tmpRoot, adapter.outputRoot);
      await mkdir(outputRoot, { recursive: true });
      try {
        await adapter.emitSurface(skillsDir, outputRoot);
      } catch (error) {
        findings.push({
          rule: `compile-${adapter.name}-failed`,
          severity: "error",
          message: `${adapter.displayName} adapter failed to emit: ${error instanceof Error ? error.message : String(error)}`,
        });
      }
    }
  } finally {
    await rm(tmpRoot, { recursive: true, force: true });
  }
  return findings;
}
