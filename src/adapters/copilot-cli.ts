import type { HarnessAdapter, PluginMetadata } from "../domain/harness.js";
import {
  buildBaseManifest,
  buildPortableAgentArtifact,
  camelCaseHooks,
} from "./_shared.js";

const COPILOT_MANIFEST_KEYS = [
  "agents",
  "skills",
  "commands",
  "hooks",
  "mcpServers",
] as const;

function buildCopilotManifest(
  metadata: PluginMetadata,
  componentPaths: Parameters<typeof buildBaseManifest>[1],
): Record<string, unknown> {
  return {
    ...buildBaseManifest(metadata, componentPaths, COPILOT_MANIFEST_KEYS),
    category: "development",
    strict: true,
  };
}

export const copilotCliAdapter: HarnessAdapter = {
  name: "copilot-cli",
  displayName: "GitHub Copilot CLI",
  outputRoot: ".copilot",
  agentDirectory: "agents",
  skillDirectory: "skills",
  defaultModel: "gpt-5",
  notes: [
    "Copilot CLI resolves plugin manifests from .claude-plugin/plugin.json as its fourth search path, so the same manifest shape serves both Claude Code and Copilot CLI installations.",
  ],
  manifestDir: ".claude-plugin",
  buildManifest: (metadata, componentPaths) =>
    buildCopilotManifest(metadata, componentPaths),
  mcpFileName: ".mcp.json",
  buildHookConfig: (portable) => ({
    version: 1,
    hooks: camelCaseHooks(portable),
  }),
  buildAgentArtifact: buildPortableAgentArtifact,
  capabilities: {
    skillFrontmatterKeys: new Set<string>(),
    agentFrontmatterKeys: new Set<string>(),
    hookEvents: new Set(["sessionStart", "preToolUse", "postToolUse"]),
    toolNames: new Set<string>(),
    bootstrapHook: true,
  },
};
