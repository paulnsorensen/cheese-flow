import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import {
  compileTestSkill,
  type HarnessCompatFinding,
} from "./harness-compat.js";
import {
  type IssueFactory,
  type LintIssue,
  lintSkillSource,
  makeIssueFactory,
} from "./lint-skill-rules.js";

export type { LintIssue, LintSeverity } from "./lint-skill-rules.js";
export { lintSkillSource };

export type LintReport = {
  scanned: number;
  issues: LintIssue[];
};

export type CompileSkillFn = (
  skillName: string,
  skillSource: string,
) => Promise<HarnessCompatFinding[]>;

export type LintSkillsDirectoryOptions = {
  compile?: CompileSkillFn;
};

export async function lintSkillsDirectory(
  skillsRoot: string,
  options: LintSkillsDirectoryOptions = {},
): Promise<LintReport> {
  const compile = options.compile ?? compileTestSkill;
  const entries = await readdir(skillsRoot, { withFileTypes: true });
  const directories = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  const issues: LintIssue[] = [];
  for (const directoryName of directories) {
    issues.push(
      ...(await lintSkillDirectory(skillsRoot, directoryName, compile)),
    );
  }

  return { scanned: directories.length, issues };
}

async function lintSkillDirectory(
  skillsRoot: string,
  directoryName: string,
  compile: CompileSkillFn,
): Promise<LintIssue[]> {
  const skillFile = path.join(skillsRoot, directoryName, "SKILL.md");
  const relativeFile = path.relative(skillsRoot, skillFile);
  const issue = makeIssueFactory(directoryName, relativeFile);

  const sourceOrIssue = await readSkillSource(skillFile, issue);
  if ("issues" in sourceOrIssue) return sourceOrIssue.issues;

  const sourceIssues = lintSkillSource({
    directoryName,
    relativeFile,
    source: sourceOrIssue.source,
  });

  // Skip the cross-harness compile-trip when the source itself has errors.
  // The compile step would re-surface the same parse/name failures four times,
  // one per adapter, drowning out the real source issue.
  if (sourceIssues.some((issue) => issue.severity === "error")) {
    return sourceIssues;
  }

  const compileFindings = await compile(directoryName, sourceOrIssue.source);
  const compileIssues = compileFindings.map((finding) =>
    findingToIssue(finding, directoryName, relativeFile),
  );

  return [...sourceIssues, ...compileIssues];
}

type SourceOk = { source: string };
type SourceFailed = { issues: LintIssue[] };

async function readSkillSource(
  skillFile: string,
  issue: IssueFactory,
): Promise<SourceOk | SourceFailed> {
  try {
    await stat(skillFile);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    return {
      issues: [
        issue(
          "error",
          "skill-md-required",
          "SKILL.md is required at the skill directory root.",
        ),
      ],
    };
  }

  try {
    return { source: await readFile(skillFile, "utf8") };
  } catch (error) {
    return {
      issues: [
        issue(
          "error",
          "skill-md-unreadable",
          `SKILL.md could not be read: ${error instanceof Error ? error.message : String(error)}`,
        ),
      ],
    };
  }
}

function findingToIssue(
  finding: HarnessCompatFinding,
  directoryName: string,
  relativeFile: string,
): LintIssue {
  return {
    skill: directoryName,
    file: relativeFile,
    severity: finding.severity,
    rule: finding.rule,
    message: finding.message,
    ...(finding.line !== undefined ? { line: finding.line } : {}),
  };
}

export function formatLintReport(report: LintReport): string {
  const lines: string[] = [
    `cheese lint — ${report.scanned} skill${report.scanned === 1 ? "" : "s"} scanned`,
    "",
  ];

  if (report.issues.length === 0) {
    lines.push("No issues found.");
    return `${lines.join("\n")}\n`;
  }

  for (const item of report.issues) {
    const tag = item.severity === "error" ? "ERROR" : "WARN";
    const anchor =
      item.line !== undefined ? `${item.file}:${item.line}` : item.file;
    lines.push(`[${tag}] ${anchor} (${item.rule}): ${item.message}`);
  }

  const errorCount = report.issues.filter(
    (entry) => entry.severity === "error",
  ).length;
  const warningCount = report.issues.length - errorCount;
  lines.push("");
  lines.push(`${errorCount} error(s), ${warningCount} warning(s).`);

  return `${lines.join("\n")}\n`;
}

export function hasErrors(report: LintReport): boolean {
  return report.issues.some((item) => item.severity === "error");
}
