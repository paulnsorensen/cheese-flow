import type {
  AgentArtifact,
  AgentArtifactInput,
  HookEntry,
  ManifestComponentPaths,
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

type ManifestComponentKey = keyof ManifestComponentPaths;

function pickManifestPaths(
  componentPaths: ManifestComponentPaths,
  supportedKeys: readonly ManifestComponentKey[],
): Record<string, string> {
  return Object.fromEntries(
    supportedKeys.flatMap((key) => {
      const value = componentPaths[key];
      return value === undefined ? [] : [[key, value]];
    }),
  );
}

export function buildBaseManifest(
  metadata: PluginMetadata,
  componentPaths: ManifestComponentPaths,
  supportedKeys: readonly ManifestComponentKey[],
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
    ...pickManifestPaths(componentPaths, supportedKeys),
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

export function buildBaseAgentArtifact(
  input: AgentArtifactInput,
  agentFrontmatterKeys: ReadonlySet<string>,
): AgentArtifact {
  const { frontmatter, resolvedModel } = input;
  const data: Record<string, unknown> = {
    name: frontmatter.name,
    description: frontmatter.description,
    model: resolvedModel,
  };
  if (frontmatter.tools.length > 0) data.tools = frontmatter.tools;
  for (const key of agentFrontmatterKeys) {
    const value = (frontmatter as unknown as Record<string, unknown>)[key];
    if (value === undefined) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    data[key] = value;
  }
  const appendix =
    agentFrontmatterKeys.has("skills") || frontmatter.skills.length === 0
      ? ""
      : buildSkillsAppendix(frontmatter.skills);
  return { frontmatter: data, appendix };
}

export function buildPortableAgentArtifact(
  input: AgentArtifactInput,
): AgentArtifact {
  return buildBaseAgentArtifact(input, EMPTY_AGENT_KEYS);
}

const EMPTY_AGENT_KEYS: ReadonlySet<string> = new Set();

function buildSkillsAppendix(skills: string[]): string {
  const lines = skills.map((skill) => `- ${skill}`).join("\n");
  return `\n## Required skills (prompt contract)\n\nThis harness does not expose a structured skills binding, so treat the\nfollowing skill names as a hard prompt contract — invoke them by name when\nthe workflow calls for their behavior:\n\n${lines}\n`;
}
