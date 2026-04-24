import type { Dirent } from "node:fs";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { Eta } from "eta";
import { parseFrontmatter } from "./frontmatter.js";
import { type HarnessName, harnessDefinitions } from "./harnesses.js";
import {
  type AgentFrontmatter,
  parseAgentFrontmatter,
  parseCommandFrontmatter,
  parseSkillFrontmatter,
  resolveModel,
  type SkillFrontmatter,
} from "./schemas.js";

const eta = new Eta({ autoEscape: false, autoTrim: false, useWith: true });

type InstallOptions = {
  projectRoot: string;
  harnesses: HarnessName[];
};

export async function installHarnessArtifacts(
  options: InstallOptions,
): Promise<string[]> {
  const outputs: string[] = [];
  for (const harnessName of options.harnesses) {
    outputs.push(await processHarness(harnessName, options.projectRoot));
  }
  return outputs;
}

async function processHarness(
  harnessName: HarnessName,
  projectRoot: string,
): Promise<string> {
  const harness = harnessDefinitions[harnessName];
  const outputRoot = path.join(projectRoot, harness.outputRoot);
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

  const agents = await compileAgents({
    projectRoot,
    harness: harnessName,
    agentOutputDirectory,
  });
  const skills = await copySkills({ projectRoot, skillOutputDirectory });
  const commands = await copyCommands({
    projectRoot,
    commandOutputDirectory,
  });

  await writeManifest(outputRoot, {
    harness: harnessName,
    agents,
    skills,
    commands,
  });
  return outputRoot;
}

type ManifestContents = {
  harness: HarnessName;
  agents: string[];
  skills: string[];
  commands: string[];
};

async function writeManifest(
  outputRoot: string,
  contents: ManifestContents,
): Promise<void> {
  const manifest = { ...contents, generatedAt: new Date().toISOString() };
  await writeFile(
    path.join(outputRoot, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
}

type CompileAgentsOptions = {
  projectRoot: string;
  harness: HarnessName;
  agentOutputDirectory: string;
};

async function compileAgents(options: CompileAgentsOptions): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "agents");
  const entries = (await readdir(sourceDirectory, { withFileTypes: true }))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
  const compiled: string[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".md.eta")) {
      continue;
    }

    const sourcePath = path.join(sourceDirectory, entry.name);
    const source = await readFile(sourcePath, "utf8");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = parseAgentFrontmatter(parsed.data);
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
  const entries = (await readdir(sourceDirectory, { withFileTypes: true }))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
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
    const frontmatter = parseSkillFrontmatter(parsed.data);

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

async function readCommandEntries(sourceDirectory: string): Promise<Dirent[]> {
  try {
    const entries = await readdir(sourceDirectory, { withFileTypes: true });
    return entries.slice().sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

async function copyCommands(options: CopyCommandsOptions): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "commands");
  const entries = await readCommandEntries(sourceDirectory);
  const copied: string[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".md")) {
      continue;
    }

    const sourcePath = path.join(sourceDirectory, entry.name);
    const parsed = parseFrontmatter<unknown>(
      await readFile(sourcePath, "utf8"),
    );
    const frontmatter = parseCommandFrontmatter(parsed.data);
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
  const frontmatter: AgentFrontmatter = parseAgentFrontmatter(parsed.data);
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
  return parseSkillFrontmatter(parsed.data);
}
