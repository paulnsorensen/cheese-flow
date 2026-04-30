import type { HarnessAdapter } from "../domain/harness.js";
import {
  buildBaseManifest,
  buildPortableAgentArtifact,
  pascalMatcherHooks,
} from "./_shared.js";

export const codexAdapter: HarnessAdapter = {
  name: "codex",
  displayName: "Codex",
  outputRoot: ".codex",
  agentDirectory: "agents",
  skillDirectory: "skills",
  commandDirectory: "commands",
  defaultModel: "gpt-5.1-codex",
  notes: [
    "Bias instructions toward patch-oriented execution and explicit constraints.",
    "Prefer Codex model identifiers in agent metadata and output.",
  ],
  manifestDir: ".codex-plugin",
  buildManifest: buildBaseManifest,
  mcpFileName: ".mcp.json",
  buildHookConfig: (portable) => ({ hooks: pascalMatcherHooks(portable) }),
  buildAgentArtifact: buildPortableAgentArtifact,
  capabilities: {
    skillFrontmatterKeys: new Set<string>(),
    agentFrontmatterKeys: new Set<string>(),
    hookEvents: new Set(["sessionStart", "preToolUse", "postToolUse"]),
    toolNames: new Set<string>(),
    bootstrapHook: true,
  },
};
