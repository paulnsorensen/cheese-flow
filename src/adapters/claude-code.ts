import type {
  HarnessAdapter,
  HookEntry,
  PortableHooks,
} from "../domain/harness.js";
import {
  buildBaseAgentArtifact,
  buildBaseManifest,
  pascalMatcherHooks,
} from "./_shared.js";

const CLAUDE_AGENT_KEYS: ReadonlySet<string> = new Set([
  "skills",
  "color",
  "effort",
  "disallowedTools",
  "permissionMode",
]);

const CLAUDE_MANIFEST_KEYS = [
  // "agents" intentionally omitted — Claude Code's plugin manifest validator
  // rejects this key (see issue #58). Files under the bundle's default
  // `./agents/` directory are auto-discovered at startup, so the conventional
  // layout cheese-flow uses still works without it. Re-add when upstream
  // accepts the field again.
  "skills",
  "commands",
  "hooks",
  "mcpServers",
] as const;

// Hook command paths must resolve from the installed plugin root in Claude
// Code, not the user's working directory. The portable `hooks.json` source
// uses `bash hooks/cheese-bootstrap.sh`; rewrite that to reference
// `${CLAUDE_PLUGIN_ROOT}` so the script is found wherever Claude Code installs
// the plugin. Other commands pass through unchanged.
const BOOTSTRAP_RELATIVE_PATH = "hooks/cheese-bootstrap.sh";

function rewriteBootstrapCommand(entry: HookEntry): HookEntry {
  if (!entry.command.includes(BOOTSTRAP_RELATIVE_PATH)) return entry;
  return {
    ...entry,
    command: entry.command.replace(
      BOOTSTRAP_RELATIVE_PATH,
      `\${CLAUDE_PLUGIN_ROOT}/${BOOTSTRAP_RELATIVE_PATH}`,
    ),
  };
}

function rewriteBootstrapPaths(portable: PortableHooks): PortableHooks {
  const result: PortableHooks = {};
  for (const [event, entries] of Object.entries(portable)) {
    if (entries === undefined) continue;
    result[event as keyof PortableHooks] = entries.map(rewriteBootstrapCommand);
  }
  return result;
}

export const claudeCodeAdapter: HarnessAdapter = {
  name: "claude-code",
  displayName: "Claude Code",
  outputRoot: ".claude",
  agentDirectory: "agents",
  skillDirectory: "skills",
  commandDirectory: "commands",
  defaultModel: "sonnet",
  notes: [
    "Use concise markdown headings and explicit tool guidance.",
    "Prefer Claude model identifiers in agent metadata and output.",
  ],
  manifestDir: ".claude-plugin",
  buildManifest: (metadata, componentPaths) =>
    buildBaseManifest(metadata, componentPaths, CLAUDE_MANIFEST_KEYS),
  mcpFileName: ".mcp.json",
  buildHookConfig: (portable) => ({
    hooks: pascalMatcherHooks(rewriteBootstrapPaths(portable)),
  }),
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
