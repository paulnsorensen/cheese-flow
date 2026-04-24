import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { HarnessName } from "./harnesses.js";

export type McpServerConfig = {
  command: string;
  args: string[];
  env?: Record<string, string>;
};

const canonicalServers: Record<string, McpServerConfig> = {
  tilth: { command: "npx", args: ["tilth", "--mcp", "--edit"] },
  tavily: {
    command: "npx",
    args: ["-y", "tavily-mcp@latest"],
    // biome-ignore lint/suspicious/noTemplateCurlyInString: MCP runtime performs env var substitution on the literal "${TAVILY_API_KEY}" pattern.
    env: { TAVILY_API_KEY: "${TAVILY_API_KEY}" },
  },
};

function resolveOutputPath(harness: HarnessName, outputRoot: string): string {
  if (harness === "cursor") {
    return path.join(outputRoot, "mcp.json");
  }
  return path.join(outputRoot, ".mcp.json");
}

export async function emitMcpConfig(
  harness: HarnessName,
  outputRoot: string,
): Promise<string> {
  await mkdir(outputRoot, { recursive: true });

  const config: Record<string, unknown> = {
    mcpServers: canonicalServers,
    __TODO_milknado__:
      "Milknado MCP server integration deferred — see milknado-mcp follow-up spec.",
  };

  const outputPath = resolveOutputPath(harness, outputRoot);
  await writeFile(outputPath, `${JSON.stringify(config, null, 2)}\n`);

  return outputPath;
}
