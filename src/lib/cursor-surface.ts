import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseFrontmatter } from "./frontmatter.js";
import type { SkillFrontmatter } from "./schemas.js";

function buildRuleContent(description: string, body: string): string {
  return `---\ndescription: ${description}\nglobs:\nalwaysApply: false\n---\n${body.trim()}\n`;
}

async function isDirectory(filePath: string): Promise<boolean> {
  try {
    const stats = await stat(filePath);
    return stats.isDirectory();
  } catch {
    return false;
  }
}

async function emitSkill(
  skillName: string,
  skillMdPath: string,
  rulesDir: string,
  commandsDir: string,
): Promise<{ rule: string; command: string } | null> {
  let content: string;
  try {
    content = await readFile(skillMdPath, "utf8");
  } catch {
    return null;
  }

  const { data, body } = parseFrontmatter<Partial<SkillFrontmatter>>(content);
  const description = data.description ?? "";

  const ruleContent = buildRuleContent(description, body);
  const commandContent = `${body.trim()}\n`;

  const rulePath = path.join(rulesDir, `${skillName}.mdc`);
  const commandPath = path.join(commandsDir, `${skillName}.md`);

  await writeFile(rulePath, ruleContent, "utf8");
  await writeFile(commandPath, commandContent, "utf8");

  return { rule: rulePath, command: commandPath };
}

export async function emitCursorSurface(
  skillsDir: string,
  outputRoot: string,
): Promise<{ rules: string[]; commands: string[] }> {
  const exists = await isDirectory(skillsDir);
  if (!exists) {
    return { rules: [], commands: [] };
  }

  const rulesDir = path.join(outputRoot, "rules");
  const commandsDir = path.join(outputRoot, "commands");
  await mkdir(rulesDir, { recursive: true });
  await mkdir(commandsDir, { recursive: true });

  const entries = await readdir(skillsDir, { withFileTypes: true });
  const rules: string[] = [];
  const commands: string[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const skillName = entry.name;
    const skillMdPath = path.join(skillsDir, skillName, "SKILL.md");
    const result = await emitSkill(
      skillName,
      skillMdPath,
      rulesDir,
      commandsDir,
    );

    if (result !== null) {
      rules.push(result.rule);
      commands.push(result.command);
    }
  }

  return { rules, commands };
}
