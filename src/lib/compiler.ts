import type { Dirent } from "node:fs";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { Eta } from "eta";
import { stringify as stringifyYaml } from "yaml";
import { harnessAdapters } from "../adapters/index.js";
import {
  type HarnessAdapter,
  type HarnessName,
  type HooksSource,
  hooksSourceSchema,
  type ManifestComponentPaths,
  type PluginMetadata,
  pluginMetadataSchema,
  type SurfaceEmissionResult,
} from "../domain/harness.js";
import { emitHooks, emitMcpConfig, emitPluginManifest } from "./emit.js";
import { parseFrontmatter } from "./frontmatter.js";
import {
  applyModelManifest,
  type ModelManifest,
  readModelManifest,
} from "./model-manifest.js";
import {
  type AgentFrontmatter,
  parseAgentFrontmatter,
  parseCommandFrontmatter,
  parseSkillFrontmatter,
  resolveModel,
  type SkillFrontmatter,
} from "./schemas.js";

function buildAgentFile(
  frontmatter: AgentFrontmatter,
  adapter: HarnessAdapter,
  resolvedModel: string,
  renderedBody: string,
): string {
  const { frontmatter: data, appendix } = adapter.buildAgentArtifact({
    frontmatter,
    resolvedModel,
  });
  return `---\n${stringifyYaml(data)}---\n${renderedBody.trimStart()}${appendix}`;
}

const DEFAULT_PLUGIN_METADATA: PluginMetadata = {
  name: "cheese-flow",
  version: "0.1.0",
  description:
    "Opinionated coding harness plugin scaffold for portable agents and skills.",
  author: { name: "Paul Sorensen" },
  license: "MIT",
  repository: "https://github.com/paulnsorensen/cheese-flow",
};

function isFileNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { code?: unknown }).code === "ENOENT"
  );
}

async function readPluginMetadata(
  projectRoot: string,
): Promise<PluginMetadata> {
  const pluginJsonPath = path.join(
    projectRoot,
    ".claude-plugin",
    "plugin.json",
  );
  let raw: string;
  try {
    raw = await readFile(pluginJsonPath, "utf8");
  } catch (error) {
    if (isFileNotFound(error)) return DEFAULT_PLUGIN_METADATA;
    throw error;
  }
  return pluginMetadataSchema.parse(JSON.parse(raw));
}

async function readHooksSource(projectRoot: string): Promise<HooksSource> {
  const hooksJsonPath = path.join(projectRoot, "hooks.json");
  let raw: string;
  try {
    raw = await readFile(hooksJsonPath, "utf8");
  } catch (error) {
    if (isFileNotFound(error)) return {};
    throw error;
  }
  return hooksSourceSchema.parse(JSON.parse(raw)) as HooksSource;
}

const eta = new Eta({ autoEscape: false, autoTrim: false, useWith: true });

type CompileBundlesOptions = {
  projectRoot: string;
  harnesses: HarnessName[];
};

type CompileHarnessBundleOptions = {
  projectRoot: string;
  harness: HarnessName;
};

export type CompiledHarnessBundle = {
  harness: HarnessName;
  outputRoot: string;
  pluginMetadata: PluginMetadata;
};

type CompileSession = {
  projectRoot: string;
  pluginMetadata: PluginMetadata;
  hooksSource: HooksSource;
  skillSourceDirectory: string;
  modelManifest: ModelManifest | null;
};

type CompileHarnessBundleContext = {
  harnessName: HarnessName;
} & CompileSession;

async function createCompileSession(
  projectRoot: string,
): Promise<CompileSession> {
  return {
    projectRoot,
    pluginMetadata: await readPluginMetadata(projectRoot),
    modelManifest: await readModelManifest(projectRoot),
    hooksSource: await readHooksSource(projectRoot),
    skillSourceDirectory: path.join(projectRoot, "skills"),
  };
}

export async function compileHarnessBundle(
  options: CompileHarnessBundleOptions,
): Promise<CompiledHarnessBundle> {
  return compileHarnessBundleFromSession({
    ...(await createCompileSession(options.projectRoot)),
    harnessName: options.harness,
  });
}

export async function compileHarnessBundles(
  options: CompileBundlesOptions,
): Promise<string[]> {
  const session = await createCompileSession(options.projectRoot);
  const outputs: string[] = [];
  for (const harnessName of options.harnesses) {
    const compiled = await compileHarnessBundleFromSession({
      ...session,
      harnessName,
    });
    outputs.push(compiled.outputRoot);
  }
  return outputs;
}

// Removes only the paths this compile step re-emits, so user-managed files at
// the harness output root (settings.local.json, personal CLAUDE.md, etc.) are
// not destroyed when contributors run `cheese compile` / `npm run compile:<harness>`.
async function cleanGeneratedArtifacts(
  adapter: HarnessAdapter,
  outputRoot: string,
): Promise<void> {
  const generatedDirectories = [
    adapter.agentDirectory,
    adapter.skillDirectory,
    adapter.commandDirectory,
    adapter.manifestDir,
  ].filter((entry): entry is string => entry !== undefined);

  if (adapter.emitSurface !== undefined) {
    generatedDirectories.push("rules", "commands");
  }

  const generatedFiles = [adapter.mcpFileName, "manifest.json"];
  if (adapter.buildHookConfig({}) !== null) {
    generatedFiles.push("hooks.json");
  }

  await Promise.all([
    ...generatedDirectories.map((entry) =>
      rm(path.join(outputRoot, entry), { recursive: true, force: true }),
    ),
    ...generatedFiles.map((entry) =>
      rm(path.join(outputRoot, entry), { force: true }),
    ),
  ]);
}

function manifestDirectoryPath(relativePath: string): string {
  return `./${relativePath}/`;
}

function manifestFilePath(relativePath: string): string {
  return `./${relativePath}`;
}

function buildManifestComponentPaths(options: {
  adapter: HarnessAdapter;
  agents: string[];
  skills: string[];
  commands: string[];
  emittedSurface: SurfaceEmissionResult;
}): ManifestComponentPaths {
  return {
    ...(options.agents.length > 0
      ? { agents: manifestDirectoryPath(options.adapter.agentDirectory) }
      : {}),
    ...(options.skills.length > 0
      ? { skills: manifestDirectoryPath(options.adapter.skillDirectory) }
      : {}),
    ...(options.commands.length > 0 &&
    options.adapter.commandDirectory !== undefined
      ? options.adapter.name === "codex"
        ? { apps: manifestDirectoryPath(options.adapter.commandDirectory) }
        : { commands: manifestDirectoryPath(options.adapter.commandDirectory) }
      : {}),
    ...(options.emittedSurface.rules.length > 0
      ? { rules: manifestDirectoryPath("rules") }
      : {}),
    ...(options.emittedSurface.commands.length > 0
      ? { commands: manifestDirectoryPath("commands") }
      : {}),
    ...(options.adapter.buildHookConfig({}) !== null
      ? { hooks: manifestFilePath("hooks.json") }
      : {}),
    mcpServers: manifestFilePath(options.adapter.mcpFileName),
  };
}

async function compileHarnessBundleFromSession(
  context: CompileHarnessBundleContext,
): Promise<CompiledHarnessBundle> {
  const adapter = harnessAdapters[context.harnessName];
  const outputRoot = path.join(context.projectRoot, adapter.outputRoot);
  const agentOutputDirectory = path.join(outputRoot, adapter.agentDirectory);
  const skillOutputDirectory = path.join(outputRoot, adapter.skillDirectory);

  await cleanGeneratedArtifacts(adapter, outputRoot);
  await mkdir(agentOutputDirectory, { recursive: true });
  await mkdir(skillOutputDirectory, { recursive: true });

  const agents = await compileAgents({
    projectRoot: context.projectRoot,
    harness: context.harnessName,
    agentOutputDirectory,
    modelManifest: context.modelManifest,
  });
  const skills = await copySkills({
    projectRoot: context.projectRoot,
    skillOutputDirectory,
  });

  let commands: string[] = [];
  if (adapter.commandDirectory !== undefined) {
    const commandOutputDirectory = path.join(
      outputRoot,
      adapter.commandDirectory,
    );
    await mkdir(commandOutputDirectory, { recursive: true });
    commands = await copyCommands({
      projectRoot: context.projectRoot,
      commandOutputDirectory,
    });
  }

  const emittedSurface =
    adapter.emitSurface === undefined
      ? { rules: [], commands: [] }
      : await adapter.emitSurface(context.skillSourceDirectory, outputRoot);
  const manifestComponentPaths = buildManifestComponentPaths({
    adapter,
    agents,
    skills,
    commands,
    emittedSurface,
  });

  await writeManifest(outputRoot, {
    harness: context.harnessName,
    agents,
    skills,
    commands,
  });

  await emitPluginManifest(
    context.harnessName,
    context.pluginMetadata,
    outputRoot,
    manifestComponentPaths,
  );
  await emitMcpConfig(context.harnessName, outputRoot);
  await emitHooks(context.harnessName, context.hooksSource, outputRoot);

  return {
    harness: context.harnessName,
    outputRoot,
    pluginMetadata: context.pluginMetadata,
  };
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
  modelManifest: ModelManifest | null;
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
    const adapter = harnessAdapters[options.harness];
    const outputFile = `${frontmatter.name}.md`;
    const baseModel = resolveModel(frontmatter.models, options.harness);
    const resolvedModel = applyModelManifest({
      model: baseModel,
      agentName: frontmatter.name,
      harness: options.harness,
      manifest: options.modelManifest,
    });
    const rendered = eta.renderString(parsed.body, {
      agent: { ...frontmatter, model: resolvedModel },
      harness: adapter,
    }) as string;

    const finalContent = buildAgentFile(
      frontmatter,
      adapter,
      resolvedModel,
      rendered,
    );

    await writeFile(
      path.join(options.agentOutputDirectory, outputFile),
      finalContent,
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
  const manifest = await readModelManifest(projectRoot);
  const baseModel = resolveModel(frontmatter.models, harness);
  const resolvedModel = applyModelManifest({
    model: baseModel,
    agentName: frontmatter.name,
    harness,
    manifest,
  });
  const rendered = eta.renderString(parsed.body, {
    agent: { ...frontmatter, model: resolvedModel },
    harness: harnessAdapters[harness],
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
