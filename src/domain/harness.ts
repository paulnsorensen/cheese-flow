import { z } from "zod";

export type HarnessName = "claude-code" | "codex" | "cursor" | "copilot-cli";

export const CHEESE_DIR = ".cheese";

export const PORTABLE_EVENTS = [
  "sessionStart",
  "preToolUse",
  "postToolUse",
] as const;
export type PortableEvent = (typeof PORTABLE_EVENTS)[number];

export type HookEntry = {
  type: string;
  command: string;
  timeout?: number;
};

const hookEntrySchema = z.object({
  type: z.string().min(1),
  command: z.string().min(1),
  timeout: z.number().int().positive().optional(),
});

export const hooksSourceSchema = z.record(z.string(), z.array(hookEntrySchema));
export type HooksSource = Partial<Record<string, HookEntry[]>>;
export type PortableHooks = Partial<Record<PortableEvent, HookEntry[]>>;

export const pluginMetadataSchema = z.object({
  name: z.string().min(1),
  version: z.string().min(1),
  description: z.string().min(1),
  author: z.object({
    name: z.string().min(1),
    email: z.string().optional(),
    url: z.string().optional(),
  }),
  license: z.string().min(1),
  repository: z.string().min(1),
  homepage: z.string().optional(),
  keywords: z.array(z.string()).optional(),
});

export type PluginMetadata = z.infer<typeof pluginMetadataSchema>;

export type McpServerConfig = {
  command: string;
  args: string[];
  env?: Record<string, string>;
};

export const canonicalMcpServers: Record<string, McpServerConfig> = {
  milknado: {
    command: "npx",
    args: ["tsx", "src/index.ts", "mcp"],
  },
  tilth: { command: "npx", args: ["tilth", "--mcp", "--edit"] },
  context7: {
    command: "npx",
    args: ["-y", "@upstash/context7-mcp"],
  },
  tavily: {
    command: "npx",
    args: ["-y", "tavily-mcp@latest"],
    // biome-ignore lint/suspicious/noTemplateCurlyInString: MCP runtime performs env var substitution on the literal "${TAVILY_API_KEY}" pattern.
    env: { TAVILY_API_KEY: "${TAVILY_API_KEY}" },
  },
};

export type SurfaceEmissionResult = {
  rules: string[];
  commands: string[];
};

export type ManifestComponentPaths = Partial<{
  agents: string;
  skills: string;
  commands: string;
  hooks: string;
  mcpServers: string;
  rules: string;
  apps: string;
}>;

export type AgentFrontmatterFields = {
  name: string;
  description: string;
  tools: string[];
  skills: string[];
  color?: string | undefined;
  effort?: string | undefined;
  disallowedTools: string[];
  permissionMode?: string | undefined;
};

export type AgentArtifactInput = {
  frontmatter: AgentFrontmatterFields;
  resolvedModel: string;
};

export type AgentArtifact = {
  frontmatter: Record<string, unknown>;
  appendix: string;
};

export type HarnessCapabilities = {
  skillFrontmatterKeys: ReadonlySet<string>;
  agentFrontmatterKeys: ReadonlySet<string>;
  hookEvents: ReadonlySet<string>;
  toolNames: ReadonlySet<string>;
  bootstrapHook: boolean;
};

export interface HarnessAdapter {
  name: HarnessName;
  displayName: string;
  outputRoot: string;
  agentDirectory: string;
  skillDirectory: string;
  commandDirectory?: string;
  defaultModel: string;
  notes: string[];

  manifestDir: string;
  buildManifest(
    metadata: PluginMetadata,
    componentPaths: ManifestComponentPaths,
  ): Record<string, unknown>;

  mcpFileName: string;

  buildHookConfig(portable: PortableHooks): Record<string, unknown> | null;

  buildAgentArtifact(input: AgentArtifactInput): AgentArtifact;

  emitSurface?: (
    skillsDir: string,
    outputRoot: string,
  ) => Promise<SurfaceEmissionResult>;

  capabilities: HarnessCapabilities;
}
