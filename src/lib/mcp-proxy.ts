import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { resolveCheeseHome } from "./cheese-home.js";

export type ProxyTransport = {
  start?(): Promise<void>;
  close(): Promise<void>;
};

export type ProxyClient = {
  connect(transport: ProxyTransport): Promise<void>;
  close(): Promise<void>;
  listTools(params?: { cursor?: string }): Promise<unknown>;
  callTool(params: {
    name: string;
    arguments?: Record<string, unknown>;
  }): Promise<unknown>;
};

export type ProxyServer = {
  onclose?: () => void;
  connect(transport: ProxyTransport): Promise<void>;
  close(): Promise<void>;
  setRequestHandler(
    schema: unknown,
    handler: (request: {
      params?: Record<string, unknown>;
    }) => Promise<unknown>,
  ): void;
};

export type ClientFactory = () => ProxyClient;
export type ServerFactory = () => ProxyServer;
export type ClientTransportFactory = (projectRoot: string) => ProxyTransport;
export type ServerTransportFactory = () => ProxyTransport;

export type RunMcpProxyOptions = {
  projectRoot: string;
  clientFactory: ClientFactory;
  serverFactory: ServerFactory;
  clientTransportFactory: ClientTransportFactory;
  serverTransportFactory: ServerTransportFactory;
  shutdownSignal?: Promise<void>;
};

function getMcpServerScriptPath(projectRoot: string): string {
  return path.join(projectRoot, "python", "mcp_server.py");
}

function getMcpServerCommand(projectRoot: string): {
  command: string;
  args: string[];
} {
  return {
    command: "uv",
    args: [
      "run",
      "--project",
      projectRoot,
      "python",
      getMcpServerScriptPath(projectRoot),
    ],
  };
}

export function wireProxyHandlers(
  server: ProxyServer,
  client: ProxyClient,
): void {
  server.setRequestHandler(ListToolsRequestSchema, async (request) => {
    const cursor =
      typeof request.params?.cursor === "string"
        ? request.params.cursor
        : undefined;
    return await client.listTools(
      cursor === undefined ? undefined : { cursor },
    );
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const params = request.params;
    if (!params || typeof params.name !== "string") {
      throw new Error("tools/call request is missing a tool name");
    }
    const name = params.name;
    const rawArgs = params.arguments;
    return await client.callTool(
      typeof rawArgs === "object" && rawArgs !== null
        ? { name, arguments: rawArgs as Record<string, unknown> }
        : { name },
    );
  });
}

export const defaultClientFactory: ClientFactory = () =>
  new Client({
    name: "cheese-flow-proxy",
    version: "0.1.0",
  }) as unknown as ProxyClient;

export const defaultServerFactory: ServerFactory = () =>
  new Server(
    { name: "cheese-flow", version: "0.1.0" },
    { capabilities: { tools: {} } },
  ) as unknown as ProxyServer;

export const defaultClientTransportFactory: ClientTransportFactory = (
  projectRoot,
) => {
  const { command, args } = getMcpServerCommand(projectRoot);
  const env = mcpServerEnv(projectRoot);
  return new StdioClientTransport({
    command,
    args,
    cwd: projectRoot,
    env,
  }) as unknown as ProxyTransport;
};

function mcpServerEnv(projectRoot: string): Record<string, string> {
  const base: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (typeof value === "string") base[key] = value;
  }
  try {
    const paths = resolveCheeseHome(projectRoot);
    base.MILKNADO_DB_PATH = paths.milknadoDb;
  } catch {
    // best-effort: if not in a git repo, fall back to in-repo default behavior
  }
  return base;
}

export const defaultServerTransportFactory: ServerTransportFactory = () =>
  new StdioServerTransport() as unknown as ProxyTransport;

export async function runMcpProxy(options: RunMcpProxyOptions): Promise<void> {
  const client = options.clientFactory();
  const server = options.serverFactory();
  const clientTransport = options.clientTransportFactory(options.projectRoot);
  const serverTransport = options.serverTransportFactory();

  const serverClosed = new Promise<void>((resolve) => {
    server.onclose = resolve;
  });
  const stop = options.shutdownSignal
    ? Promise.race([serverClosed, options.shutdownSignal])
    : serverClosed;

  try {
    await connectClientOrExplain(client, clientTransport);
    wireProxyHandlers(server, client);
    await server.connect(serverTransport);
    await stop;
  } finally {
    await server.close().catch(() => undefined);
    await client.close().catch(() => undefined);
  }
}

async function connectClientOrExplain(
  client: ProxyClient,
  transport: ProxyTransport,
): Promise<void> {
  try {
    await client.connect(transport);
  } catch (error) {
    if (isMissingUvSpawnError(error)) {
      throw new Error(
        'Unable to run the MCP proxy because "uv" was not found on PATH. Install uv from https://docs.astral.sh/uv/.',
      );
    }
    throw error;
  }
}

function isMissingUvSpawnError(error: unknown): boolean {
  if (!(error instanceof Error) || !("code" in error)) {
    return false;
  }
  const errno = error as NodeJS.ErrnoException;
  if (errno.code !== "ENOENT") {
    return false;
  }
  return errno.path === "uv" || /\buv\b/.test(error.message);
}
