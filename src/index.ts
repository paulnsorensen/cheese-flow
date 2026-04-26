#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Command, InvalidArgumentError } from "commander";
import { harnessNames } from "./adapters/index.js";
import type { HarnessName } from "./domain/harness.js";
import { installHarnessArtifacts } from "./lib/compiler.js";
import {
  formatReport,
  hasBlockingFailure,
  runAllToolChecks,
} from "./lib/doctor.js";
import { runInitWizard } from "./lib/init-wizard.js";
import {
  defaultClientFactory,
  defaultClientTransportFactory,
  defaultServerFactory,
  defaultServerTransportFactory,
  runMcpProxy,
} from "./lib/mcp-proxy.js";
import { runMilknadoCommand } from "./lib/milknado.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const defaultProjectRoot = path.resolve(__dirname, "..");

function parseHarness(value: string): HarnessName {
  if (harnessNames.includes(value as HarnessName)) {
    return value as HarnessName;
  }

  throw new InvalidArgumentError(
    `Unsupported harness "${value}". Expected one of: ${harnessNames.join(", ")}.`,
  );
}

const program = new Command();

program
  .name("cheese")
  .description(
    "Compile portable agents and Agent Skills into harness-specific markdown bundles.",
  )
  .version("0.1.0");

program
  .command("init")
  .description(
    "Interactive setup wizard — pick harnesses and install dependencies.",
  )
  .option(
    "--project-root <path>",
    "Project root that contains ./agents and ./skills.",
    defaultProjectRoot,
  )
  .action(async (options: { projectRoot: string }) => {
    await runInitWizard({ projectRoot: path.resolve(options.projectRoot) });
  });

program
  .command("install")
  .description(
    "Compile the repository skill and agent sources for one or more target harnesses.",
  )
  .option(
    "-H, --harness <name...>",
    "Harness target(s) to install for.",
    (value, previous: HarnessName[] | undefined) => {
      const items = Array.isArray(previous) ? previous : [];
      return [
        ...items,
        ...value.split(",").map((item) => parseHarness(item.trim())),
      ];
    },
    [] as HarnessName[],
  )
  .option(
    "--project-root <path>",
    "Project root that contains ./agents and ./skills.",
    defaultProjectRoot,
  )
  .action(async (options: { harness: HarnessName[]; projectRoot: string }) => {
    const targets =
      options.harness.length > 0
        ? Array.from(new Set(options.harness))
        : harnessNames;
    const outputs = await installHarnessArtifacts({
      projectRoot: path.resolve(options.projectRoot),
      harnesses: targets,
    });

    for (const output of outputs) {
      process.stdout.write(`Compiled harness bundle: ${output}\n`);
    }
  });

program
  .command("doctor")
  .description(
    "Verify required, recommended, and suggested CLI tools are installed.",
  )
  .action(async () => {
    const results = await runAllToolChecks();
    process.stdout.write(formatReport(results));
    if (hasBlockingFailure(results)) {
      process.exitCode = 1;
    }
  });

program
  .command("milknado")
  .description("Run the sample Python backend and print its TUI.")
  .option(
    "--project-root <path>",
    "Project root that contains ./python and pyproject.toml.",
    defaultProjectRoot,
  )
  .action(async (options: { projectRoot: string }) => {
    await runMilknadoCommand({
      projectRoot: path.resolve(options.projectRoot),
    });
  });

program
  .command("mcp")
  .description(
    "Run the MCP proxy: a TS stdio MCP server that forwards to a long-lived Python MCP server spawned via uv.",
  )
  .option(
    "--project-root <path>",
    "Project root that contains ./python/mcp_server.py and pyproject.toml.",
    defaultProjectRoot,
  )
  .action(async (options: { projectRoot: string }) => {
    const shutdownSignal = new Promise<void>((resolve) => {
      const onSignal = () => resolve();
      process.once("SIGINT", onSignal);
      process.once("SIGTERM", onSignal);
    });
    await runMcpProxy({
      projectRoot: path.resolve(options.projectRoot),
      clientFactory: defaultClientFactory,
      serverFactory: defaultServerFactory,
      clientTransportFactory: defaultClientTransportFactory,
      serverTransportFactory: defaultServerTransportFactory,
      shutdownSignal,
    });
  });

program.parseAsync(process.argv).catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
