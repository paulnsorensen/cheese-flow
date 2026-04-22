#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Command, InvalidArgumentError } from "commander";
import { installHarnessArtifacts } from "./lib/compiler.js";
import { type HarnessName, harnessDefinitions } from "./lib/harnesses.js";
import { runMilknadoCommand } from "./lib/milknado.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const defaultProjectRoot = path.resolve(__dirname, "..");

const harnessNames = Object.keys(harnessDefinitions) as HarnessName[];

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
  .name("cheese-flow")
  .description(
    "Compile portable agents and Agent Skills into harness-specific markdown bundles.",
  )
  .version("0.1.0");

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
  .command("milknado")
  .description("Run the sample Python backend and print its TUI.")
  .option(
    "--project-root <path>",
    "Project root that contains ./python.",
    defaultProjectRoot,
  )
  .action(async (options: { projectRoot: string }) => {
    await runMilknadoCommand({
      projectRoot: path.resolve(options.projectRoot),
    });
  });

program.parseAsync(process.argv).catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
