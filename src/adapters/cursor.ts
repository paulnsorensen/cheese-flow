import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type {
  HarnessAdapter,
  SurfaceEmissionResult,
} from "../domain/harness.js";
import { parseFrontmatter } from "../lib/frontmatter.js";
import type { SkillFrontmatter } from "../lib/schemas.js";
import { buildBaseManifest, buildPortableAgentArtifact } from "./_shared.js";

const CURSOR_MANIFEST_KEYS = [
  "rules",
  "skills",
  "agents",
  "commands",
  "hooks",
  "mcpServers",
] as const;

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

async function emitCursorSkillSurface(
  skillsDir: string,
  outputRoot: string,
): Promise<SurfaceEmissionResult> {
  const exists = await isDirectory(skillsDir);
  if (!exists) return { rules: [], commands: [] };

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

export const cursorAdapter: HarnessAdapter = {
  name: "cursor",
  displayName: "Cursor",
  outputRoot: ".cursor",
  agentDirectory: "agents",
  skillDirectory: "skills",
  defaultModel: "auto",
  notes: [
    "Cursor exposes skills on two surfaces: ambient rules (.cursor/rules/*.mdc) and slash commands (.cursor/commands/*.md). Both are emitted from the same SKILL.md source.",
    "MCP-only tool surface applies; Cursor does not support hooks — hook emission is skipped with an info log.",
  ],
  manifestDir: ".cursor-plugin",
  buildManifest: (metadata, componentPaths) =>
    buildBaseManifest(metadata, componentPaths, CURSOR_MANIFEST_KEYS),
  mcpFileName: "mcp.json",
  buildHookConfig: () => null,
  buildAgentArtifact: buildPortableAgentArtifact,
  emitSurface: emitCursorSkillSurface,
  capabilities: {
    skillFrontmatterKeys: new Set<string>(),
    agentFrontmatterKeys: new Set<string>(),
    hookEvents: new Set<string>(),
    toolNames: new Set<string>(),
    bootstrapHook: false,
  },
};
