import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { harnessAdapters } from "../adapters/index.js";
import {
  canonicalMcpServers,
  type HarnessName,
  type HooksSource,
  type PluginMetadata,
  PORTABLE_EVENTS,
  type PortableEvent,
  type PortableHooks,
  pluginMetadataSchema,
} from "../domain/harness.js";

function filterPortableEvents(source: HooksSource): PortableHooks {
  const portable: PortableHooks = {};
  const portableSet: ReadonlySet<string> = new Set(PORTABLE_EVENTS);

  for (const [event, entries] of Object.entries(source)) {
    if (entries === undefined) continue;
    if (portableSet.has(event)) {
      portable[event as PortableEvent] = entries;
    } else {
      console.warn(`[cheese-flow] skipping non-portable hook event: ${event}`);
    }
  }

  return portable;
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

  const adapter = harnessAdapters[harness];
  const manifest = adapter.buildManifest(parsed.data);
  const manifestDir = path.join(outputRoot, adapter.manifestDir);

  await mkdir(manifestDir, { recursive: true });
  const manifestPath = path.join(manifestDir, "plugin.json");
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return manifestPath;
}

export async function emitMcpConfig(
  harness: HarnessName,
  outputRoot: string,
): Promise<string> {
  await mkdir(outputRoot, { recursive: true });

  const config: Record<string, unknown> = {
    mcpServers: canonicalMcpServers,
    __TODO_milknado__:
      "Milknado MCP server integration deferred — see milknado-mcp follow-up spec.",
  };

  const adapter = harnessAdapters[harness];
  const outputPath = path.join(outputRoot, adapter.mcpFileName);
  await writeFile(outputPath, `${JSON.stringify(config, null, 2)}\n`);
  return outputPath;
}

export async function emitHooks(
  harness: HarnessName,
  source: HooksSource,
  outputRoot: string,
): Promise<false | string> {
  const adapter = harnessAdapters[harness];
  const portable = filterPortableEvents(source);
  const payload = adapter.buildHookConfig(portable);

  if (payload === null) {
    console.info(
      `[cheese-flow] hooks not supported in ${harness} target; skipping`,
    );
    return false;
  }

  await mkdir(outputRoot, { recursive: true });
  const outputPath = path.join(outputRoot, "hooks.json");
  await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return outputPath;
}
