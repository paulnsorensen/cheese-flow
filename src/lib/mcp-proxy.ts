import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

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

type RequestHandlerSchema = unknown;
type RequestHandler = (request: {
  params?: Record<string, unknown>;
}) => Promise<unknown>;

export type ProxyServer = {
  onclose?: () => void;
  connect(transport: ProxyTransport): Promise<void>;
  close(): Promise<void>;
  setRequestHandler(
    schema: RequestHandlerSchema,
    handler: RequestHandler,
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

export function getMcpServerScriptPath(projectRoot: string): string {
  return path.join(projectRoot, "python", "mcp_server.py");
}

export function getMcpServerCommand(projectRoot: string): {
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
    return await client.callTool(
      request.params as {
        name: string;
        arguments?: Record<string, unknown>;
      },
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
  return new StdioClientTransport({
    command,
    args,
    cwd: projectRoot,
  }) as unknown as ProxyTransport;
};

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
    try {
      await client.connect(clientTransport);
    } catch (error) {
      if (isMissingUvError(error)) {
        throw new Error(
          'Unable to run the MCP proxy because "uv" was not found on PATH. Install uv from https://docs.astral.sh/uv/.',
        );
      }
      throw error;
    }
    wireProxyHandlers(server, client);
    await server.connect(serverTransport);
    await stop;
  } finally {
    await server.close().catch(() => undefined);
    await client.close().catch(() => undefined);
  }
}

function isMissingUvError(error: unknown): boolean {
  return (
    error instanceof Error &&
    "code" in error &&
    (error as NodeJS.ErrnoException).code === "ENOENT"
  );
}
