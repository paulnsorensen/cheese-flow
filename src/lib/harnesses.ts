export type HarnessName = "claude-code" | "codex" | "cursor" | "copilot-cli";

type HarnessDefinition = {
  name: HarnessName;
  displayName: string;
  outputRoot: string;
  agentDirectory: string;
  skillDirectory: string;
  commandDirectory?: string;
  defaultModel: string;
  notes: string[];
};

export const harnessDefinitions: Record<HarnessName, HarnessDefinition> = {
  "claude-code": {
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
  },
  codex: {
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
  },
  cursor: {
    name: "cursor",
    displayName: "Cursor",
    outputRoot: ".cursor",
    agentDirectory: "agents",
    skillDirectory: "rules",
    defaultModel: "auto",
    notes: [
      "Cursor exposes skills on two surfaces: ambient rules (.cursor/rules/*.mdc) and slash commands (.cursor/commands/*.md). Both are emitted from the same SKILL.md source by cursor-surface.ts.",
      "MCP-only tool surface applies; Cursor does not support hooks — hook emission is skipped with an info log.",
    ],
  },
  "copilot-cli": {
    name: "copilot-cli",
    displayName: "GitHub Copilot CLI",
    outputRoot: ".copilot",
    agentDirectory: "agents",
    skillDirectory: "skills",
    defaultModel: "gpt-5",
    notes: [
      "Copilot CLI resolves plugin manifests from .claude-plugin/plugin.json as its fourth search path, so the same manifest shape serves both Claude Code and Copilot CLI installations.",
    ],
  },
};
