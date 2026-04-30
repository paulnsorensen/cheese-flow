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
import type { HarnessAdapter, HarnessName } from "../domain/harness.js";
import { eventSupport, fieldSupport, toolSupport } from "./capabilities.js";
import { parseFrontmatter } from "./frontmatter.js";
import { parseSkillFrontmatter } from "./schemas.js";

export type HarnessCompatFinding = {
  rule: string;
  severity: "error" | "warning";
  message: string;
  line?: number;
};

const CLAUDE_PERMISSION_GLOB = /\b([A-Za-z]\w*)\(([^)]*:[^)]*)\)/u;

const HARNESS_PATH_MARKERS = [
  ".claude/",
  ".claude-plugin/",
  ".codex/",
  ".cursor/",
  ".copilot/",
  "AGENTS.md",
  "copilot-instructions.md",
] as const;

function displayName(harness: HarnessName): string {
  return harnessAdapters[harness].displayName;
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

export function checkFrontmatterPortability(
  frontmatter: Record<string, unknown>,
  kind: "skill" | "agent",
): HarnessCompatFinding[] {
  const support = fieldSupport(kind);
  const allAdapters = Object.keys(harnessAdapters) as HarnessName[];
  const findings: HarnessCompatFinding[] = [];

  for (const [key, supportedBy] of support) {
    if (frontmatter[key] === undefined) continue;
    if (supportedBy.length === allAdapters.length) continue;
    if (key === "context" && frontmatter[key] === "inline") continue;

    const unsupported = allAdapters.filter((n) => !supportedBy.includes(n));
    const supportedNames = supportedBy.map(displayName).join(", ");
    const unsupportedNames = unsupported.map(displayName).join(", ");
    findings.push({
      rule: "frontmatter-portability",
      severity: "warning",
      message: `frontmatter field "${key}" is supported only by ${supportedNames}; ${unsupportedNames} drop it. Move the constraint into the body, or accept the field will be ignored.`,
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
  return [
    ...collectToolFindings(body),
    ...collectEventFindings(body),
    ...collectPathFindings(body),
    ...collectPlaceholderFindings(body),
  ];
}

function collectPlaceholderFindings(body: string): HarnessCompatFinding[] {
  const line = findFirstMatchLine(body, /<harness>\//u);
  if (line === undefined) return [];
  return [
    {
      rule: "body-harness-placeholder",
      severity: "error",
      message:
        'body uses the "<harness>/" placeholder; replace with ".cheese/" so all four harnesses share a single project-root runtime directory.',
      line,
    },
  ];
}

function collectToolFindings(body: string): HarnessCompatFinding[] {
  const allAdapters = Object.keys(harnessAdapters) as HarnessName[];
  const findings: HarnessCompatFinding[] = [];
  for (const [tool, supportedBy] of toolSupport()) {
    const line = findFirstMatchLine(body, new RegExp(`\\b${tool}\\(`, "u"));
    if (line === undefined) continue;
    const unsupportedNames = allAdapters
      .filter((n) => !supportedBy.includes(n))
      .map(displayName)
      .join(", ");
    findings.push({
      rule: "body-claude-only-tool",
      severity: "warning",
      message: `body references tool "${tool}(...)"; ${unsupportedNames} do not expose this tool. Rephrase generically (e.g. "spawn a sub-agent").`,
      line,
    });
  }
  return findings;
}

function collectEventFindings(body: string): HarnessCompatFinding[] {
  const allAdapters = Object.keys(harnessAdapters) as HarnessName[];
  const hookAdapterCount = allAdapters.filter(
    (n) => harnessAdapters[n].capabilities.hookEvents.size > 0,
  ).length;
  const findings: HarnessCompatFinding[] = [];
  for (const [camelEvent, supportedBy] of eventSupport()) {
    const pascalEvent = `${camelEvent.charAt(0).toUpperCase()}${camelEvent.slice(1)}`;
    const line = findFirstMatchLine(
      body,
      new RegExp(`\\b${pascalEvent}\\b`, "u"),
    );
    if (line === undefined) continue;
    findings.push(
      eventFinding(
        camelEvent,
        pascalEvent,
        supportedBy,
        hookAdapterCount,
        allAdapters,
        line,
      ),
    );
  }
  return findings;
}

function eventFinding(
  camelEvent: string,
  pascalEvent: string,
  supportedBy: HarnessName[],
  hookAdapterCount: number,
  allAdapters: HarnessName[],
  line: number,
): HarnessCompatFinding {
  if (supportedBy.length === hookAdapterCount) {
    return {
      rule: "body-pascal-hook-event",
      severity: "warning",
      message: `body references PascalCase hook event "${pascalEvent}"; cheese-flow's portable hooks use camelCase ("${camelEvent}"). Per-harness mapping is applied at compile time.`,
      line,
    };
  }
  const unsupported = allAdapters.filter((n) => !supportedBy.includes(n));
  const supportedNames = supportedBy.map(displayName).join(", ");
  const unsupportedNames = unsupported.map(displayName).join(", ");
  return {
    rule: "body-harness-only-hook-event",
    severity: "warning",
    message: `body references hook event "${pascalEvent}" which is supported only by ${supportedNames}; ${unsupportedNames} do not expose it.`,
    line,
  };
}

function collectPathFindings(body: string): HarnessCompatFinding[] {
  const findings: HarnessCompatFinding[] = [];
  for (const marker of HARNESS_PATH_MARKERS) {
    const line = findFirstMatchLine(body, new RegExp(escapeRegex(marker), "u"));
    if (line === undefined) continue;
    findings.push({
      rule: "body-harness-path-marker",
      severity: "warning",
      message: `body references harness-specific path "${marker}"; portable skills should use the cheese-flow source layout (e.g. "skills/<name>/SKILL.md") and let adapters project per harness.`,
      line,
    });
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
