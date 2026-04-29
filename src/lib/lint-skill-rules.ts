import { z } from "zod";
import { parseFrontmatter } from "./frontmatter.js";
import {
  checkAllowedToolsPortability,
  checkBodyHarnessIdioms,
  checkFrontmatterPortability,
} from "./harness-compat.js";
import { parseSkillFrontmatter, type SkillFrontmatter } from "./schemas.js";

export type LintSeverity = "error" | "warning";

export type LintIssue = {
  skill: string;
  file: string;
  severity: LintSeverity;
  rule: string;
  message: string;
  line?: number;
};

export type IssueFactory = (
  severity: LintSeverity,
  rule: string,
  message: string,
  line?: number,
) => LintIssue;

export type LintSourceContext = {
  directoryName: string;
  relativeFile: string;
  source: string;
};

const RECOMMENDED_BODY_LINE_LIMIT = 500;
const MIN_DESCRIPTION_LENGTH = 20;

export function makeIssueFactory(
  directoryName: string,
  relativeFile: string,
): IssueFactory {
  return (severity, rule, message, line) => ({
    skill: directoryName,
    file: relativeFile,
    severity,
    rule,
    message,
    ...(line !== undefined ? { line } : {}),
  });
}

export function lintSkillSource(context: LintSourceContext): LintIssue[] {
  const issue = makeIssueFactory(context.directoryName, context.relativeFile);

  let parsed: { data: unknown; body: string };
  try {
    parsed = parseFrontmatter<unknown>(context.source);
  } catch (error) {
    return [
      issue(
        "error",
        "frontmatter-parse",
        error instanceof Error ? error.message : String(error),
      ),
    ];
  }

  const issues: LintIssue[] = [];
  issues.push(...validateFrontmatter(parsed.data, context, issue));
  issues.push(
    ...validateBody(parsed.body, bodyLineOffset(context.source), issue),
  );
  return issues;
}

function bodyLineOffset(source: string): number {
  // SKILL.md line N for body line 1 = lines consumed by "---\n<frontmatter>\n---\n".
  const bodyStart = source.search(/\r?\n---\r?\n/u);
  if (bodyStart === -1) return 0;
  const lead = source.slice(0, bodyStart);
  const headerLines = lead.split(/\r?\n/u).length;
  return headerLines + 1;
}

function validateFrontmatter(
  data: unknown,
  context: LintSourceContext,
  issue: IssueFactory,
): LintIssue[] {
  const issues: LintIssue[] = [];
  const frontmatter = tryParseFrontmatter(data, issue, issues);

  if (frontmatter !== undefined) {
    issues.push(...nameAndDescriptionChecks(frontmatter, context, issue));
  }

  if (typeof data === "object" && data !== null) {
    const raw = data as Record<string, unknown>;
    issues.push(...portabilityChecks(raw["allowed-tools"], raw, issue));
  }

  return issues;
}

function tryParseFrontmatter(
  data: unknown,
  issue: IssueFactory,
  issues: LintIssue[],
): SkillFrontmatter | undefined {
  try {
    return parseSkillFrontmatter(data);
  } catch (error) {
    if (error instanceof z.ZodError) {
      for (const zodIssue of error.issues) {
        const fieldPath = zodIssue.path.join(".") || "<frontmatter>";
        issues.push(
          issue(
            "error",
            `frontmatter:${fieldPath}`,
            `${fieldPath}: ${zodIssue.message}`,
          ),
        );
      }
    } else {
      issues.push(
        issue(
          "error",
          "frontmatter-parse",
          error instanceof Error ? error.message : String(error),
        ),
      );
    }
    return undefined;
  }
}

function nameAndDescriptionChecks(
  frontmatter: SkillFrontmatter,
  context: LintSourceContext,
  issue: IssueFactory,
): LintIssue[] {
  const issues: LintIssue[] = [];
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
  return issues;
}

function portabilityChecks(
  allowedTools: unknown,
  rawFrontmatter: Record<string, unknown>,
  issue: IssueFactory,
): LintIssue[] {
  const issues: LintIssue[] = [];
  const allowed =
    typeof allowedTools === "string" || Array.isArray(allowedTools)
      ? (allowedTools as string | string[])
      : undefined;
  for (const finding of checkAllowedToolsPortability(allowed)) {
    issues.push(issue(finding.severity, finding.rule, finding.message));
  }
  for (const finding of checkFrontmatterPortability(rawFrontmatter, "skill")) {
    issues.push(issue(finding.severity, finding.rule, finding.message));
  }
  return issues;
}

function validateBody(
  body: string,
  lineOffset: number,
  issue: IssueFactory,
): LintIssue[] {
  const issues: LintIssue[] = [];
  const bodyLineCount = body.split(/\r?\n/u).length;
  if (bodyLineCount > RECOMMENDED_BODY_LINE_LIMIT) {
    issues.push(
      issue(
        "warning",
        "body-too-long",
        `SKILL.md body is ${bodyLineCount} lines; the spec recommends staying under ${RECOMMENDED_BODY_LINE_LIMIT}. Move detail into references/.`,
      ),
    );
  }
  for (const finding of checkBodyHarnessIdioms(body)) {
    const absoluteLine =
      finding.line !== undefined ? finding.line + lineOffset : undefined;
    issues.push(
      issue(finding.severity, finding.rule, finding.message, absoluteLine),
    );
  }
  return issues;
}
