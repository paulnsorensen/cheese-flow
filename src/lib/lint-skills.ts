import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { z } from "zod";
import { parseFrontmatter } from "./frontmatter.js";
import { parseSkillFrontmatter } from "./schemas.js";

export type LintSeverity = "error" | "warning";

export type LintIssue = {
  skill: string;
  file: string;
  severity: LintSeverity;
  rule: string;
  message: string;
};

export type LintReport = {
  scanned: number;
  issues: LintIssue[];
};

const RECOMMENDED_BODY_LINE_LIMIT = 500;
const MIN_DESCRIPTION_LENGTH = 20;

export async function lintSkillsDirectory(
  skillsRoot: string,
): Promise<LintReport> {
  const entries = await readdir(skillsRoot, { withFileTypes: true });
  const directories = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  const issues: LintIssue[] = [];
  for (const directoryName of directories) {
    issues.push(...(await lintSkillDirectory(skillsRoot, directoryName)));
  }

  return { scanned: directories.length, issues };
}

async function lintSkillDirectory(
  skillsRoot: string,
  directoryName: string,
): Promise<LintIssue[]> {
  const skillDirectory = path.join(skillsRoot, directoryName);
  const skillFile = path.join(skillDirectory, "SKILL.md");
  const relativeFile = path.relative(skillsRoot, skillFile);

  try {
    await stat(skillFile);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    return [
      {
        skill: directoryName,
        file: relativeFile,
        severity: "error",
        rule: "skill-md-required",
        message: "SKILL.md is required at the skill directory root.",
      },
    ];
  }

  let source: string;
  try {
    source = await readFile(skillFile, "utf8");
  } catch {
    return [
      {
        skill: directoryName,
        file: relativeFile,
        severity: "error",
        rule: "skill-md-required",
        message: "SKILL.md could not be read.",
      },
    ];
  }
  return lintSkillSource({
    directoryName,
    relativeFile,
    source,
  });
}

type LintSourceContext = {
  directoryName: string;
  relativeFile: string;
  source: string;
};

export function lintSkillSource(context: LintSourceContext): LintIssue[] {
  const issues: LintIssue[] = [];
  const issue = (
    severity: LintSeverity,
    rule: string,
    message: string,
  ): LintIssue => ({
    skill: context.directoryName,
    file: context.relativeFile,
    severity,
    rule,
    message,
  });

  let parsed: { data: unknown; body: string };
  try {
    parsed = parseFrontmatter<unknown>(context.source);
  } catch (error) {
    issues.push(issue("error", "frontmatter-parse", (error as Error).message));
    return issues;
  }

  try {
    const frontmatter = parseSkillFrontmatter(parsed.data);

    if (frontmatter.name !== context.directoryName) {
      issues.push(
        issue(
          "error",
          "name-matches-directory",
          `frontmatter name "${frontmatter.name}" must match parent directory "${context.directoryName}".`,
        ),
      );
    }

    const description = frontmatter.description.trim();
    if (description.length < MIN_DESCRIPTION_LENGTH) {
      issues.push(
        issue(
          "warning",
          "description-too-short",
          `description is ${description.length} chars; aim for at least ${MIN_DESCRIPTION_LENGTH} so agents can match it during discovery.`,
        ),
      );
    }
  } catch (error) {
    const zodError = error as z.ZodError;
    for (const zodIssue of zodError.issues) {
      const fieldPath = zodIssue.path.join(".") || "<frontmatter>";
      issues.push(
        issue(
          "error",
          `frontmatter:${fieldPath}`,
          `${fieldPath}: ${zodIssue.message}`,
        ),
      );
    }
  }

  const bodyLineCount = parsed.body.split(/\r?\n/u).length;
  if (bodyLineCount > RECOMMENDED_BODY_LINE_LIMIT) {
    issues.push(
      issue(
        "warning",
        "body-too-long",
        `SKILL.md body is ${bodyLineCount} lines; the spec recommends staying under ${RECOMMENDED_BODY_LINE_LIMIT}. Move detail into references/.`,
      ),
    );
  }

  return issues;
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
    lines.push(`[${tag}] ${item.file} (${item.rule}): ${item.message}`);
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
