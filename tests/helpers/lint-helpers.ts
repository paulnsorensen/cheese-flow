import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const createdDirectories: string[] = [];

export async function createSkillsRoot(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "cheese-lint-"));
  createdDirectories.push(root);
  return root;
}

export async function writeSkill(
  skillsRoot: string,
  directoryName: string,
  contents: string,
): Promise<void> {
  const directory = path.join(skillsRoot, directoryName);
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "SKILL.md"), contents, "utf8");
}

export async function cleanupSkillRoots(): Promise<void> {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
}

export const validBody = "# Skill body\n\nUse this skill to do a thing.\n";
