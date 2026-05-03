#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Command, InvalidArgumentError } from "commander";
import { harnessNames } from "./adapters/index.js";
import type { HarnessName } from "./domain/harness.js";
import { compileHarnessBundles } from "./lib/compiler.js";
import {
  formatReport,
  hasBlockingFailure,
  runAllToolChecks,
} from "./lib/doctor.js";
import {
  formatLintReport,
  hasErrors,
  lintSkillsDirectory,
} from "./lib/lint-skills.js";
import {
  defaultClientFactory,
  defaultClientTransportFactory,
  defaultServerFactory,
  defaultServerTransportFactory,
  runMcpProxy,
} from "./lib/mcp-proxy.js";
import { runMilknadoCommand } from "./lib/milknado.js";
import { runSessionStart } from "./lib/session-start.js";

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

type CompileCommandOptions = {
  harness: HarnessName[];
  projectRoot: string;
};

function resolveHarnessTargets(harness: HarnessName[]): HarnessName[] {
  return harness.length > 0 ? Array.from(new Set(harness)) : harnessNames;
}

async function runCompileCommand(
  options: CompileCommandOptions,
): Promise<void> {
  const outputs = await compileHarnessBundles({
    projectRoot: path.resolve(options.projectRoot),
    harnesses: resolveHarnessTargets(options.harness),
  });

  for (const output of outputs) {
    process.stdout.write(`Compiled harness bundle: ${output}\n`);
  }
}

function failInstallPlaceholder(): never {
  throw new Error(
    "`cheese install` is reserved for local harness installation and is not implemented yet. Use `cheese compile` to emit harness bundles.",
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
  .command("compile")
  .description(
    "Compile the repository skill and agent sources into one or more harness bundles.",
  )
  .option(
    "-H, --harness <name...>",
    "Harness target(s) to compile for. Defaults to all supported harnesses.",
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
  .action(runCompileCommand);

program
  .command("install")
  .description(
    "Install generated bundles into a local harness workspace. (Not implemented yet.)",
  )
  .action(() => {
    failInstallPlaceholder();
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
  .command("lint")
  .description(
    "Lint skills/ against the Agent Skills format (https://agentskills.io).",
  )
  .option(
    "--project-root <path>",
    "Project root that contains ./skills.",
    defaultProjectRoot,
  )
  .action(async (options: { projectRoot: string }) => {
    const skillsDirectory = path.join(
      path.resolve(options.projectRoot),
      "skills",
    );
    const report = await lintSkillsDirectory(skillsDirectory);
    process.stdout.write(formatLintReport(report));
    if (hasErrors(report)) {
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
  .command("session-start")
  .description(
    "Run cheese-flow housekeeping (sweep + update check) under a soft time budget. Best-effort; never blocks session start.",
  )
  .option("--root <path>", "project root", process.cwd())
  .option("--quiet", "suppress non-error output", false)
  .option("--max-time <ms>", "soft budget for housekeeping", "5000")
  .action(
    async (options: { root: string; quiet: boolean; maxTime: string }) => {
      try {
        await runSessionStart({
          cwd: path.resolve(options.root),
          maxTimeMs: Number.parseInt(options.maxTime, 10) || 5000,
          currentVersion: "0.1.0",
          quiet: options.quiet,
        });
      } catch {
        // Best-effort: never block session start on housekeeping failure.
      }
      process.exit(0);
    },
  );

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
