import type { Dirent } from "node:fs";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { Eta } from "eta";
import { harnessAdapters } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";
import { parseFrontmatter } from "./frontmatter.js";
import {
  type AgentFrontmatter,
  parseAgentFrontmatter,
  resolveModel,
} from "./schemas.js";

const eta = new Eta({ autoEscape: false, autoTrim: false, useWith: true });

export type CompileAgentsOptions = {
  projectRoot: string;
  harness: HarnessName;
  agentOutputDirectory: string;
};

export async function compileAgents(
  options: CompileAgentsOptions,
): Promise<string[]> {
  const sourceDirectory = path.join(options.projectRoot, "agents");
  const partials = await loadAgentPartials(sourceDirectory);
  const entries = await listAgentTemplates(sourceDirectory);
  const compiled: string[] = [];

  for (const entry of entries) {
    const sourcePath = path.join(sourceDirectory, entry.name);
    const source = await readFile(sourcePath, "utf8");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = parseAgentFrontmatter(parsed.data);
    const outputFile = `${frontmatter.name}.md`;
    const rendered = renderAgent(parsed.body, frontmatter, options.harness, {
      partials,
    });

    await writeFile(
      path.join(options.agentOutputDirectory, outputFile),
      rendered.trimStart(),
      "utf8",
    );
    compiled.push(outputFile);
  }

  return compiled;
}

async function listAgentTemplates(sourceDirectory: string): Promise<Dirent[]> {
  const entries = await readdir(sourceDirectory, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md.eta"))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
}

function renderAgent(
  body: string,
  frontmatter: AgentFrontmatter,
  harness: HarnessName,
  context: { partials: Record<string, string> },
): string {
  return eta.renderString(body, {
    agent: {
      ...frontmatter,
      model: resolveModel(frontmatter.models, harness),
    },
    harness: harnessAdapters[harness],
    partials: context.partials,
  }) as string;
}

export async function previewAgent(
  projectRoot: string,
  agentFile: string,
  harness: HarnessName,
): Promise<string> {
  const agentsDir = path.join(projectRoot, "agents");
  const sourcePath = path.join(agentsDir, agentFile);
  const source = await readFile(sourcePath, "utf8");
  const parsed = parseFrontmatter<unknown>(source);
  const frontmatter = parseAgentFrontmatter(parsed.data);
  const partials = await loadAgentPartials(agentsDir);
  const rendered = renderAgent(parsed.body, frontmatter, harness, { partials });
  return rendered.trim();
}

async function loadAgentPartials(
  agentsDirectory: string,
): Promise<Record<string, string>> {
  const partialsDir = path.join(agentsDirectory, "_partials");
  let entries: Dirent[];
  try {
    entries = await readdir(partialsDir, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
  const partials: Record<string, string> = {};
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const baseName = entry.name.replace(/\.md(\.eta)?$/u, "");
    const camelKey = baseName.replace(/-([a-z0-9])/gu, (_, c: string) =>
      c.toUpperCase(),
    );
    partials[camelKey] = (
      await readFile(path.join(partialsDir, entry.name), "utf8")
    ).trim();
  }
  return partials;
}
