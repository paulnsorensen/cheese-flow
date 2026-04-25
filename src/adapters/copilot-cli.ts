import type { HarnessAdapter, PluginMetadata } from "../domain/harness.js";
import { buildBaseManifest, camelCaseHooks } from "./_shared.js";

function buildCopilotManifest(
  metadata: PluginMetadata,
): Record<string, unknown> {
  return {
    ...buildBaseManifest(metadata),
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
  buildManifest: buildCopilotManifest,
  mcpFileName: ".mcp.json",
  buildHookConfig: (portable) => ({
    version: 1,
    hooks: camelCaseHooks(portable),
  }),
};
