import type { HarnessAdapter } from "../domain/harness.js";
import {
  buildBaseAgentArtifact,
  buildBaseManifest,
  camelCaseHooks,
} from "./_shared.js";

const CLAUDE_AGENT_KEYS: ReadonlySet<string> = new Set([
  "skills",
  "color",
  "effort",
  "disallowedTools",
  "permissionMode",
]);

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
  buildAgentArtifact: (input) =>
    buildBaseAgentArtifact(input, CLAUDE_AGENT_KEYS),
  capabilities: {
    skillFrontmatterKeys: new Set(["model", "context"]),
    agentFrontmatterKeys: CLAUDE_AGENT_KEYS,
    hookEvents: new Set([
      "sessionStart",
      "sessionEnd",
      "preToolUse",
      "postToolUse",
      "stop",
      "subagentStop",
      "notification",
      "preCompact",
      "userPromptSubmit",
    ]),
    toolNames: new Set([
      "Agent",
      "Task",
      "NotebookEdit",
      "WebSearch",
      "WebFetch",
      "TodoWrite",
    ]),
    bootstrapHook: true,
  },
};
