import {
  cp,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { harnessAdapters } from "../adapters/index.js";
import type { HarnessAdapter } from "../domain/harness.js";
import { parseFrontmatter } from "./frontmatter.js";
import {
  CLAUDE_ONLY_AGENT_KEYS,
  CLAUDE_ONLY_SKILL_KEYS,
  parseSkillFrontmatter,
} from "./schemas.js";

export type HarnessCompatFinding = {
  rule: string;
  severity: "error" | "warning";
  message: string;
  line?: number;
};

const CLAUDE_PERMISSION_GLOB = /\b([A-Za-z]\w*)\(([^)]*:[^)]*)\)/u;

const CLAUDE_ONLY_TOOL_NAMES = [
  "Agent",
  "Task",
  "NotebookEdit",
  "WebSearch",
  "WebFetch",
  "TodoWrite",
] as const;

const PASCAL_HOOK_EVENTS = [
  "SessionStart",
  "SessionEnd",
  "PreToolUse",
  "PostToolUse",
  "Stop",
  "SubagentStop",
  "Notification",
  "PreCompact",
  "UserPromptSubmit",
] as const;

const HARNESS_PATH_MARKERS = [
  ".claude/",
  ".claude-plugin/",
  ".codex/",
  ".cursor/",
  ".copilot/",
  "AGENTS.md",
  "copilot-instructions.md",
] as const;

export function checkContextPortability(
  context: string | undefined,
): HarnessCompatFinding[] {
  if (context !== "fork") return [];
  return [
    {
      rule: "context-fork-claude-only",
      severity: "warning",
      message:
        "context: fork is a Claude Code-only hint (forked subagent context). Codex, Cursor, and Copilot CLI ignore it — the skill body must still work when run inline. Document the fallback or set context: inline for harness-portable skills.",
    },
  ];
}

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

export function checkClaudeOnlyFields(
  frontmatter: Record<string, unknown>,
  kind: "skill" | "agent",
): HarnessCompatFinding[] {
  const claudeOnlyKeys =
    kind === "skill" ? CLAUDE_ONLY_SKILL_KEYS : CLAUDE_ONLY_AGENT_KEYS;
  const findings: HarnessCompatFinding[] = [];
  for (const key of claudeOnlyKeys) {
    if (frontmatter[key] === undefined) continue;
    if (key === "context" && frontmatter[key] === "inline") continue;
    findings.push({
      rule: `frontmatter-claude-only-field`,
      severity: "warning",
      message: `frontmatter field "${key}" is Claude Code-only and is dropped by Codex, Cursor, and Copilot CLI. Move the constraint into the body, or accept that non-Claude harnesses will ignore it.`,
    });
  }
  return findings;
}

function lineNumberOf(source: string, index: number): number {
  let line = 1;
  for (let i = 0; i < index && i < source.length; i++) {
    if (source[i] === "\n") line++;
  }
  return line;
}

function findFirstMatchLine(body: string, pattern: RegExp): number | undefined {
  const match = body.match(new RegExp(pattern.source, "u"));
  if (!match || match.index === undefined) return undefined;
  return lineNumberOf(body, match.index);
}

export function checkBodyHarnessIdioms(body: string): HarnessCompatFinding[] {
  const findings: HarnessCompatFinding[] = [];

  for (const tool of CLAUDE_ONLY_TOOL_NAMES) {
    const pattern = new RegExp(`\\b${tool}\\(`, "u");
    const line = findFirstMatchLine(body, pattern);
    if (line !== undefined) {
      findings.push({
        rule: "body-claude-only-tool",
        severity: "warning",
        message: `body references Claude-only tool "${tool}(...)"; non-Claude harnesses do not expose this tool. Rephrase generically (e.g. "spawn a sub-agent").`,
        line,
      });
    }
  }

  for (const event of PASCAL_HOOK_EVENTS) {
    const camel = `${event.charAt(0).toLowerCase()}${event.slice(1)}`;
    const pattern = new RegExp(`\\b${event}\\b`, "u");
    const line = findFirstMatchLine(body, pattern);
    if (line !== undefined) {
      findings.push({
        rule: "body-pascal-hook-event",
        severity: "warning",
        message: `body references PascalCase hook event "${event}"; cheese-flow's portable hooks use camelCase ("${camel}"). Per-harness mapping is applied at compile time.`,
        line,
      });
    }
  }

  for (const marker of HARNESS_PATH_MARKERS) {
    const pattern = new RegExp(escapeRegex(marker), "u");
    const line = findFirstMatchLine(body, pattern);
    if (line !== undefined) {
      findings.push({
        rule: "body-harness-path-marker",
        severity: "warning",
        message: `body references harness-specific path "${marker}"; portable skills should use the cheese-flow source layout (e.g. "skills/<name>/SKILL.md") and let adapters project per harness.`,
        line,
      });
    }
  }

  return findings;
}

function escapeRegex(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
}

async function setupSkillDir(
  tmpRoot: string,
  skillName: string,
  skillSource: string,
): Promise<string> {
  const skillsDir = path.join(tmpRoot, "skills");
  await mkdir(path.join(skillsDir, skillName), { recursive: true });
  await writeFile(
    path.join(skillsDir, skillName, "SKILL.md"),
    skillSource,
    "utf8",
  );
  return skillsDir;
}

async function tryAdapterInstall(
  adapter: HarnessAdapter,
  skillsDir: string,
  tmpRoot: string,
): Promise<HarnessCompatFinding | null> {
  const outputRoot = path.join(tmpRoot, adapter.outputRoot);
  const skillOutputRoot = path.join(outputRoot, adapter.skillDirectory);
  try {
    await mkdir(skillOutputRoot, { recursive: true });
    await simulateCopySkills(skillsDir, skillOutputRoot);
    if (adapter.emitSurface !== undefined) {
      await adapter.emitSurface(skillsDir, outputRoot);
    }
    return null;
  } catch (error) {
    return {
      rule: `compile-${adapter.name}-failed`,
      severity: "error",
      message: `${adapter.displayName} adapter failed to emit: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

async function simulateCopySkills(
  skillsDir: string,
  skillOutputRoot: string,
): Promise<void> {
  const entries = await readdir(skillsDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const skillReadmePath = path.join(skillsDir, entry.name, "SKILL.md");
    const content = await readFile(skillReadmePath, "utf8");
    const parsed = parseFrontmatter<unknown>(content);
    const frontmatter = parseSkillFrontmatter(parsed.data);
    if (frontmatter.name !== entry.name) {
      throw new Error(
        `Skill directory "${entry.name}" must match frontmatter name "${frontmatter.name}".`,
      );
    }
    await cp(
      path.join(skillsDir, entry.name),
      path.join(skillOutputRoot, entry.name),
      { recursive: true, force: true },
    );
  }
}

export async function compileTestSkill(
  skillName: string,
  skillSource: string,
): Promise<HarnessCompatFinding[]> {
  const findings: HarnessCompatFinding[] = [];
  const tmpRoot = await mkdtemp(path.join(os.tmpdir(), "cheese-compile-"));
  try {
    const skillsDir = await setupSkillDir(tmpRoot, skillName, skillSource);
    for (const adapter of Object.values(harnessAdapters)) {
      const finding = await tryAdapterInstall(adapter, skillsDir, tmpRoot);
      if (finding !== null) findings.push(finding);
    }
  } finally {
    await rm(tmpRoot, { recursive: true, force: true });
  }
  return findings;
}
