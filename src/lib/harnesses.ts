export type HarnessName = "claude-code" | "codex";

type HarnessDefinition = {
  name: HarnessName;
  displayName: string;
  outputRoot: string;
  agentDirectory: string;
  skillDirectory: string;
  commandDirectory: string;
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
};
