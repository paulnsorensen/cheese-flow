import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it, vi } from "vitest";
import {
  defaultClientFactory,
  defaultClientTransportFactory,
  defaultServerFactory,
  defaultServerTransportFactory,
  getMcpServerCommand,
  getMcpServerScriptPath,
  type ProxyClient,
  type ProxyServer,
  type ProxyTransport,
  runMcpProxy,
  wireProxyHandlers,
} from "../src/lib/mcp-proxy.js";

const execFileAsync = promisify(execFile);

describe("mcp-proxy helpers", () => {
  it("builds the MCP server script path relative to the project root", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");

    expect(getMcpServerScriptPath(projectRoot)).toBe(
      path.join(projectRoot, "python", "mcp_server.py"),
    );
  });

  it("builds the uv command for the MCP server", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");

    expect(getMcpServerCommand(projectRoot)).toEqual({
      command: "uv",
      args: [
        "run",
        "--project",
        projectRoot,
        "python",
        path.join(projectRoot, "python", "mcp_server.py"),
      ],
    });
  });
});

describe("wireProxyHandlers", () => {
  it("forwards tools/list and tools/call to the downstream client", async () => {
    const client: ProxyClient = {
      connect: vi.fn(),
      close: vi.fn(),
      listTools: vi.fn().mockResolvedValue({ tools: [{ name: "blend_plan" }] }),
      callTool: vi.fn().mockResolvedValue({ content: [{ type: "text" }] }),
    };

    const handlers = new Map<unknown, (request: unknown) => Promise<unknown>>();
    const server: ProxyServer = {
      connect: vi.fn(),
      close: vi.fn(),
      setRequestHandler: vi.fn((schema, handler) => {
        handlers.set(schema, handler as (request: unknown) => Promise<unknown>);
      }),
    };

    wireProxyHandlers(server, client);
    expect(handlers.size).toBe(2);

    const [listSchema, callSchema] = Array.from(handlers.keys());
    const listHandler = handlers.get(listSchema);
    const callHandler = handlers.get(callSchema);

    await expect(listHandler?.({ params: {} })).resolves.toEqual({
      tools: [{ name: "blend_plan" }],
    });
    expect(client.listTools).toHaveBeenCalledTimes(1);

    await expect(
      callHandler?.({ params: { name: "blend_plan", arguments: { x: 1 } } }),
    ).resolves.toEqual({ content: [{ type: "text" }] });
    expect(client.callTool).toHaveBeenCalledWith({
      name: "blend_plan",
      arguments: { x: 1 },
    });
  });
});

describe("runMcpProxy", () => {
  it("connects client and server, wires handlers, waits on shutdown, and closes both", async () => {
    const client = createMockClient();
    const server = createMockServer();
    const clientTransport = createMockTransport();
    const serverTransport = createMockTransport();
    const shutdownSignal = Promise.resolve();

    await runMcpProxy({
      projectRoot: "/tmp/project",
      clientFactory: () => client,
      serverFactory: () => server,
      clientTransportFactory: () => clientTransport,
      serverTransportFactory: () => serverTransport,
      shutdownSignal,
    });

    expect(client.connect).toHaveBeenCalledWith(clientTransport);
    expect(server.setRequestHandler).toHaveBeenCalledTimes(2);
    expect(server.connect).toHaveBeenCalledWith(serverTransport);
    expect(server.close).toHaveBeenCalledTimes(1);
    expect(client.close).toHaveBeenCalledTimes(1);
  });

  it("shuts down when the server's onclose callback fires (no shutdown signal)", async () => {
    const client = createMockClient();
    const server = createMockServer();

    const runPromise = runMcpProxy({
      projectRoot: "/tmp/project",
      clientFactory: () => client,
      serverFactory: () => server,
      clientTransportFactory: () => createMockTransport(),
      serverTransportFactory: () => createMockTransport(),
    });

    await waitUntil(() => server.onclose !== undefined);
    server.onclose?.();

    await expect(runPromise).resolves.toBeUndefined();
    expect(client.close).toHaveBeenCalledTimes(1);
  });

  it("swallows close errors from server and client to preserve shutdown", async () => {
    const client = createMockClient();
    const server = createMockServer();
    server.close = vi.fn().mockRejectedValue(new Error("server close boom"));
    client.close = vi.fn().mockRejectedValue(new Error("client close boom"));

    await expect(
      runMcpProxy({
        projectRoot: "/tmp/project",
        clientFactory: () => client,
        serverFactory: () => server,
        clientTransportFactory: () => createMockTransport(),
        serverTransportFactory: () => createMockTransport(),
        shutdownSignal: Promise.resolve(),
      }),
    ).resolves.toBeUndefined();

    expect(server.close).toHaveBeenCalledTimes(1);
    expect(client.close).toHaveBeenCalledTimes(1);
  });

  it("propagates client connect failures and still attempts to close", async () => {
    const client = createMockClient();
    const server = createMockServer();
    client.connect = vi.fn().mockRejectedValue(new Error("spawn failed"));

    await expect(
      runMcpProxy({
        projectRoot: "/tmp/project",
        clientFactory: () => client,
        serverFactory: () => server,
        clientTransportFactory: () => createMockTransport(),
        serverTransportFactory: () => createMockTransport(),
        shutdownSignal: Promise.resolve(),
      }),
    ).rejects.toThrow(/spawn failed/u);

    expect(server.connect).not.toHaveBeenCalled();
  });
});

describe("default factories", () => {
  it("constructs real SDK instances without connecting", () => {
    const client = defaultClientFactory();
    const server = defaultServerFactory();
    const clientTransport = defaultClientTransportFactory("/tmp/project");
    const serverTransport = defaultServerTransportFactory();

    expect(typeof client.connect).toBe("function");
    expect(typeof client.close).toBe("function");
    expect(typeof server.connect).toBe("function");
    expect(typeof server.setRequestHandler).toBe("function");
    expect(typeof clientTransport.close).toBe("function");
    expect(typeof serverTransport.close).toBe("function");
  });
});

describe("mcp CLI", () => {
  it("wires up the mcp help without spawning uv or Python", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "mcp", "--help"],
      { cwd: path.resolve(".") },
    );

    expect(stdout).toContain("mcp");
    expect(stdout).toContain("Usage:");
    expect(stdout).toContain(
      "Project root that contains ./python/mcp_server.py",
    );
  });
});

function createMockClient(): ProxyClient {
  return {
    connect: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    listTools: vi.fn().mockResolvedValue({ tools: [] }),
    callTool: vi.fn().mockResolvedValue({ content: [] }),
  };
}

function createMockServer(): ProxyServer {
  return {
    connect: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    setRequestHandler: vi.fn(),
  };
}

function createMockTransport(): ProxyTransport {
  return {
    close: vi.fn().mockResolvedValue(undefined),
  };
}

async function waitUntil(predicate: () => boolean): Promise<void> {
  for (let attempts = 0; attempts < 50; attempts += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error("waitUntil condition never became true");
}
