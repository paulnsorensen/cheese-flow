import type { HarnessAdapter } from "../domain/harness.js";
import { buildBaseManifest, camelCaseHooks } from "./_shared.js";

export const claudeCodeAdapter: HarnessAdapter = {
  name: "claude-code",
  displayName: "Claude Code",
  outputRoot: ".claude",
  agentDirectory: "agents",
  skillDirectory: "skills",
  commandDirectory: "commands",
  defaultModel: "claude-sonnet-4-5",
  notes: [
    "Use concise markdown headings and explicit tool guidance.",
    "Prefer Claude model identifiers in agent metadata and output.",
  ],
  manifestDir: ".claude-plugin",
  buildManifest: buildBaseManifest,
  mcpFileName: ".mcp.json",
  buildHookConfig: (portable) => ({ hooks: camelCaseHooks(portable) }),
};
