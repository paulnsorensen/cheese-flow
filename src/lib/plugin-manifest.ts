import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { HarnessName } from "./harnesses.js";

export const pluginMetadataSchema = z.object({
  name: z.string().min(1),
  version: z.string().min(1),
  description: z.string().min(1),
  author: z.object({
    name: z.string().min(1),
    email: z.string().optional(),
    url: z.string().optional(),
  }),
  license: z.string().min(1),
  repository: z.string().min(1),
  homepage: z.string().optional(),
  keywords: z.array(z.string()).optional(),
});

export type PluginMetadata = z.infer<typeof pluginMetadataSchema>;

const manifestDirByHarness: Record<HarnessName, string> = {
  "claude-code": ".claude-plugin",
  "copilot-cli": ".claude-plugin",
  cursor: ".cursor-plugin",
  codex: ".codex-plugin",
};

function buildBaseManifest(metadata: PluginMetadata): Record<string, unknown> {
  return {
    name: metadata.name,
    version: metadata.version,
    description: metadata.description,
    author: metadata.author,
    license: metadata.license,
    repository: metadata.repository,
    ...(metadata.homepage !== undefined ? { homepage: metadata.homepage } : {}),
    ...(metadata.keywords !== undefined ? { keywords: metadata.keywords } : {}),
  };
}

function buildCopilotManifest(
  metadata: PluginMetadata,
): Record<string, unknown> {
  return {
    ...buildBaseManifest(metadata),
    category: "development",
    strict: true,
  };
}

function buildCursorManifest(
  metadata: PluginMetadata,
): Record<string, unknown> {
  return {
    name: metadata.name,
    version: metadata.version,
    description: metadata.description,
    author: metadata.author,
    license: metadata.license,
    repository: metadata.repository,
  };
}

function buildCodexManifest(metadata: PluginMetadata): Record<string, unknown> {
  const manifest: Record<string, unknown> = {
    name: metadata.name,
    version: metadata.version,
    description: metadata.description,
    author: metadata.author,
    license: metadata.license,
    repository: metadata.repository,
  };
  if (metadata.homepage !== undefined) manifest.homepage = metadata.homepage;
  if (metadata.keywords !== undefined) manifest.keywords = metadata.keywords;
  return manifest;
}

function buildManifest(
  harness: HarnessName,
  metadata: PluginMetadata,
): Record<string, unknown> {
  if (harness === "copilot-cli") return buildCopilotManifest(metadata);
  if (harness === "cursor") return buildCursorManifest(metadata);
  if (harness === "codex") return buildCodexManifest(metadata);
  return buildBaseManifest(metadata);
}

export async function emitPluginManifest(
  harness: HarnessName,
  metadata: PluginMetadata,
  outputRoot: string,
): Promise<string> {
  const parsed = pluginMetadataSchema.safeParse(metadata);
  if (!parsed.success) {
    throw new Error(
      `Plugin metadata validation failed: ${parsed.error.message}`,
    );
  }

  const manifest = buildManifest(harness, parsed.data);
  const manifestDir = path.join(outputRoot, manifestDirByHarness[harness]);

  await mkdir(manifestDir, { recursive: true });

  const manifestPath = path.join(manifestDir, "plugin.json");
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

  return manifestPath;
}
