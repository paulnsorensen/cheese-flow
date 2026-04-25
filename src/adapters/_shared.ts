import type {
  HookEntry,
  PluginMetadata,
  PortableHooks,
} from "../domain/harness.js";
import { PORTABLE_EVENTS } from "../domain/harness.js";

const PASCAL_MAP: Record<(typeof PORTABLE_EVENTS)[number], string> = {
  sessionStart: "SessionStart",
  preToolUse: "PreToolUse",
  postToolUse: "PostToolUse",
};

const DEFAULT_HOOK_TIMEOUT = 600;

export function buildBaseManifest(
  metadata: PluginMetadata,
): Record<string, unknown> {
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

export function camelCaseHooks(
  portable: PortableHooks,
): Record<string, HookEntry[]> {
  const result: Record<string, HookEntry[]> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries !== undefined) result[event] = entries;
  }
  return result;
}

export function pascalMatcherHooks(
  portable: PortableHooks,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries === undefined) continue;
    result[PASCAL_MAP[event]] = entries.map((entry) => ({
      matcher: "*",
      hooks: [
        {
          type: entry.type,
          command: entry.command,
          timeout: entry.timeout ?? DEFAULT_HOOK_TIMEOUT,
        },
      ],
    }));
  }
  return result;
}
