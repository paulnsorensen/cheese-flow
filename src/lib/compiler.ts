import type { Dirent } from "node:fs";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { Eta } from "eta";
import { parseFrontmatter } from "./frontmatter.js";
import { type HarnessName, harnessDefinitions } from "./harnesses.js";
import {
  type AgentFrontmatter,
  agentFrontmatterSchema,
  commandFrontmatterSchema,
  resolveModel,
  type SkillFrontmatter,
  skillFrontmatterSchema,
} from "./schemas.js";

const eta = new Eta({ autoEscape: false, autoTrim: false, useWith: true });

export type InstallOptions = {
  projectRoot: string;
  harnesses: HarnessName[];
};

export async function installHarnessArtifacts(
  options: InstallOptions,
): Promise<string[]> {
  const outputs: string[] = [];

  for (const harnessName of options.harnesses) {
    const harness = harnessDefinitions[harnessName];
    const outputRoot = path.join(options.projectRoot, harness.outputRoot);
    const agentOutputDirectory = path.join(outputRoot, harness.agentDirectory);
    const skillOutputDirectory = path.join(outputRoot, harness.skillDirectory);
    const commandOutputDirectory = path.join(
      outputRoot,
      harness.commandDirectory,
    );

    await rm(outputRoot, { recursive: true, force: true });
    await mkdir(agentOutputDirectory, { recursive: true });
    await mkdir(skillOutputDirectory, { recursive: true });
    await mkdir(commandOutputDirectory, { recursive: true });

    const compiledAgents = await compileAgents({
      projectRoot: options.projectRoot,
      harness: harnessName,
      agentOutputDirectory,
    });

    const copiedSkills = await copySkills({
      projectRoot: options.projectRoot,
      skillOutputDirectory,
    });

    const copiedCommands = await copyCommands({
      projectRoot: options.projectRoot,
      commandOutputDirectory,
    });

    const manifestPath = path.join(outputRoot, "manifest.json");
    const manifest = {
      harness: harnessName,
      generatedAt: new Date().toISOString(),
      agents: compiledAgents,
      skills: copiedSkills,
      commands: copiedCommands,
    };

    await writeFile(
      manifestPath,
      `${JSON.stringify(manifest, null, 2)}\n`,
      "utf8",
    );
    outputs.push(outputRoot);
  }

  return outputs;
}

type CompileAgentsOptions = {
  projectRoot: string;
  harness: HarnessName;
  agentOutputDirectory: string;
};

async function compileAgents(options: CompileAgentsOptions): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "agents");
  const entries = await readdir(sourceDirectory, { withFileTypes: true });
  const compiled: string[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".md.eta")) {
      continue;
    }

    const sourcePath = path.join(sourceDirectory, entry.name);
    const source = await readFile(sourcePath, "utf8");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = agentFrontmatterSchema.parse(parsed.data);
    const harness = harnessDefinitions[options.harness];
    const outputFile = `${frontmatter.name}.md`;
    const rendered = eta.renderString(parsed.body, {
      agent: {
        ...frontmatter,
        model: resolveModel(frontmatter.models, options.harness),
      },
      harness,
    }) as string;

    await writeFile(
      path.join(options.agentOutputDirectory, outputFile),
      rendered.trimStart(),
      "utf8",
    );
    compiled.push(outputFile);
  }

  return compiled;
}

type CopySkillsOptions = {
  projectRoot: string;
  skillOutputDirectory: string;
};

async function copySkills(options: CopySkillsOptions): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "skills");
  const entries = await readdir(sourceDirectory, { withFileTypes: true });
  const copied: string[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const skillDirectory = path.join(sourceDirectory, entry.name);
    const skillReadmePath = path.join(skillDirectory, "SKILL.md");
    const parsed = parseFrontmatter<unknown>(
      await readFile(skillReadmePath, "utf8"),
    );
    const frontmatter = skillFrontmatterSchema.parse(parsed.data);

    if (frontmatter.name !== entry.name) {
      throw new Error(
        `Skill directory "${entry.name}" must match frontmatter name "${frontmatter.name}".`,
      );
    }

    await cp(
      skillDirectory,
      path.join(options.skillOutputDirectory, entry.name),
      {
        recursive: true,
        force: true,
      },
    );
    copied.push(entry.name);
  }

  return copied;
}

type CopyCommandsOptions = {
  projectRoot: string;
  commandOutputDirectory: string;
};

async function copyCommands(options: CopyCommandsOptions): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "commands");
  let entries: Dirent[];
  try {
    entries = await readdir(sourceDirectory, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }
  const copied: string[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".md")) {
      continue;
    }

    const sourcePath = path.join(sourceDirectory, entry.name);
    const parsed = parseFrontmatter<unknown>(
      await readFile(sourcePath, "utf8"),
    );
    const frontmatter = commandFrontmatterSchema.parse(parsed.data);
    const baseName = entry.name.replace(/\.md$/u, "");

    if (frontmatter.name !== baseName) {
      throw new Error(
        `Command file "${entry.name}" must match frontmatter name "${frontmatter.name}".`,
      );
    }

    await cp(
      sourcePath,
      path.join(options.commandOutputDirectory, entry.name),
      {
        force: true,
      },
    );
    copied.push(entry.name);
  }

  return copied;
}

export async function previewAgent(
  projectRoot: string,
  agentFile: string,
  harness: HarnessName,
): Promise<string> {
  const sourcePath = path.join(projectRoot, "agents", agentFile);
  const source = await readFile(sourcePath, "utf8");
  const parsed = parseFrontmatter<unknown>(source);
  const frontmatter: AgentFrontmatter = agentFrontmatterSchema.parse(
    parsed.data,
  );
  const rendered = eta.renderString(parsed.body, {
    agent: {
      ...frontmatter,
      model: resolveModel(frontmatter.models, harness),
    },
    harness: harnessDefinitions[harness],
  }) as string;

  return rendered.trim();
}

export async function readSkill(
  projectRoot: string,
  skillName: string,
): Promise<SkillFrontmatter> {
  const sourcePath = path.join(projectRoot, "skills", skillName, "SKILL.md");
  const source = await readFile(sourcePath, "utf8");
  const parsed = parseFrontmatter<unknown>(source);
  return skillFrontmatterSchema.parse(parsed.data);
}
