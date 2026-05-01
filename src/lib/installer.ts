import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { harnessAdapters } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";
import {
  type CompiledHarnessBundle,
  compileHarnessBundle,
} from "./compiler.js";
import {
  findCommandOnPath,
  type HarnessDetectionEnvironment,
} from "./harness-detection.js";
import {
  createHarnessInstallPlan,
  dedupeHarnessNames,
  type HarnessInstallPlan,
  type HarnessSelectionMode,
} from "./install-plan.js";
import {
  writeClaudeMarketplace,
  writeCodexMarketplace,
} from "./local-marketplaces.js";

type CommandExecutionResult = {
  stdout: string;
  stderr: string;
};

type CommandExecutor = (
  command: string,
  args: string[],
  cwd: string,
) => Promise<CommandExecutionResult>;

type InstallEnvironment = HarnessDetectionEnvironment & {
  executeCommand?: CommandExecutor;
};

export type HarnessInstallState = "installed" | "manual" | "skipped" | "failed";

export type HarnessInstallReportEntry = {
  harness: HarnessName;
  displayName: string;
  state: HarnessInstallState;
  reason: string;
  outputRoot?: string;
  nextSteps: string[];
};

export type InstallReport = {
  selectionMode: HarnessSelectionMode;
  results: HarnessInstallReportEntry[];
  ok: boolean;
  guidance?: string;
};

type InstallHarnessesOptions = {
  projectRoot: string;
  requestedHarnesses?: readonly HarnessName[];
  environment?: InstallEnvironment;
};

type SelectedInstallContext = {
  bundle: CompiledHarnessBundle;
  findCommand: (command: string) => Promise<string | null>;
  executeCommand: CommandExecutor;
};

type Phase1InstallResult = {
  state: Exclude<HarnessInstallState, "skipped">;
  reason: string;
  nextSteps: string[];
};

const execFileAsync = promisify(execFile);

function shellQuote(value: string): string {
  return JSON.stringify(value);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function commandFailureMessage(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const stderr = (error as { stderr?: unknown }).stderr;
    if (typeof stderr === "string" && stderr.trim().length > 0) {
      return stderr.trim();
    }
    const stdout = (error as { stdout?: unknown }).stdout;
    if (typeof stdout === "string" && stdout.trim().length > 0) {
      return stdout.trim();
    }
  }
  return errorMessage(error);
}

async function defaultCommandExecutor(
  command: string,
  args: string[],
  cwd: string,
): Promise<CommandExecutionResult> {
  return execFileAsync(command, args, { cwd });
}

function buildSkippedEntry(
  projectRoot: string,
  harness: HarnessName,
  reason: string,
): HarnessInstallReportEntry {
  const adapter = harnessAdapters[harness];
  return {
    harness,
    displayName: adapter.displayName,
    state: "skipped",
    reason,
    outputRoot: path.join(projectRoot, adapter.outputRoot),
    nextSteps: [],
  };
}

function buildSelectedEntry(
  bundle: CompiledHarnessBundle,
  result: Phase1InstallResult,
): HarnessInstallReportEntry {
  const adapter = harnessAdapters[bundle.harness];
  return {
    harness: bundle.harness,
    displayName: adapter.displayName,
    state: result.state,
    reason: result.reason,
    outputRoot: bundle.outputRoot,
    nextSteps: result.nextSteps,
  };
}

function buildCompileFailureEntry(
  projectRoot: string,
  harness: HarnessName,
  error: unknown,
): HarnessInstallReportEntry {
  const adapter = harnessAdapters[harness];
  return {
    harness,
    displayName: adapter.displayName,
    state: "failed",
    reason: `Failed to compile ${adapter.outputRoot}: ${errorMessage(error)}`,
    outputRoot: path.join(projectRoot, adapter.outputRoot),
    nextSteps: [],
  };
}

async function installSelectedHarness(
  projectRoot: string,
  harness: HarnessName,
  context: Omit<SelectedInstallContext, "bundle">,
): Promise<HarnessInstallReportEntry> {
  let bundle: CompiledHarnessBundle;
  try {
    bundle = await compileHarnessBundle({ projectRoot, harness });
  } catch (error) {
    return buildCompileFailureEntry(projectRoot, harness, error);
  }

  const result = await runPhase1Install({
    ...context,
    bundle,
  });
  return buildSelectedEntry(bundle, result);
}

async function installSelectedHarnesses(
  plan: HarnessInstallPlan,
  options: InstallHarnessesOptions,
): Promise<Map<HarnessName, HarnessInstallReportEntry>> {
  const selectedEntries = new Map<HarnessName, HarnessInstallReportEntry>();
  const findCommand = options.environment?.findCommand ?? findCommandOnPath;
  const executeCommand =
    options.environment?.executeCommand ?? defaultCommandExecutor;

  for (const harness of plan.selectedHarnesses) {
    selectedEntries.set(
      harness,
      await installSelectedHarness(options.projectRoot, harness, {
        findCommand,
        executeCommand,
      }),
    );
  }

  return selectedEntries;
}

function orderResults(
  plan: HarnessInstallPlan,
  projectRoot: string,
  selectedEntries: Map<HarnessName, HarnessInstallReportEntry>,
): HarnessInstallReportEntry[] {
  const skippedEntries = plan.entries
    .filter((entry) => entry.selection === "skipped")
    .map((entry) =>
      buildSkippedEntry(projectRoot, entry.harness, entry.reason),
    );

  return [
    ...plan.selectedHarnesses.flatMap((harness) => {
      const selected = selectedEntries.get(harness);
      return selected === undefined ? [] : [selected];
    }),
    ...skippedEntries,
  ];
}

function isSuccessful(entry: HarnessInstallReportEntry): boolean {
  return entry.state === "installed" || entry.state === "skipped";
}

export async function installHarnesses(
  options: InstallHarnessesOptions,
): Promise<InstallReport> {
  const requestedHarnesses = dedupeHarnessNames(
    options.requestedHarnesses ?? [],
  );
  const plan = await createHarnessInstallPlan({
    projectRoot: options.projectRoot,
    requestedHarnesses,
    ...(options.environment !== undefined
      ? { environment: options.environment }
      : {}),
  });

  if (!plan.ok) {
    return {
      selectionMode: plan.selectionMode,
      results: plan.entries.map((entry) =>
        buildSkippedEntry(options.projectRoot, entry.harness, entry.reason),
      ),
      ok: false,
      ...(plan.guidance !== undefined ? { guidance: plan.guidance } : {}),
    };
  }

  const selectedEntries = await installSelectedHarnesses(plan, options);
  const results = orderResults(plan, options.projectRoot, selectedEntries);
  return {
    selectionMode: plan.selectionMode,
    results,
    ok: results.every(isSuccessful),
  };
}

export function hasBlockingInstallResult(report: InstallReport): boolean {
  return !report.ok;
}

function formatEntry(entry: HarnessInstallReportEntry): string[] {
  const lines = [`[${entry.state}] ${entry.displayName}`];
  if (entry.outputRoot !== undefined) {
    lines.push(`  Bundle: ${entry.outputRoot}`);
  }
  lines.push(`  ${entry.reason}`);
  if (entry.nextSteps.length > 0) {
    lines.push("  Next steps:");
    lines.push(...entry.nextSteps.map((step) => `  - ${step}`));
  }
  return lines;
}

export function formatInstallReport(report: InstallReport): string {
  const lines = report.results.flatMap((entry) => [...formatEntry(entry), ""]);
  if (report.guidance !== undefined) {
    lines.push(`Guidance: ${report.guidance}`, "");
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

async function runPhase1Install(
  context: SelectedInstallContext,
): Promise<Phase1InstallResult> {
  switch (context.bundle.harness) {
    case "cursor":
      return installCursorBundle(context.bundle);
    case "copilot-cli":
      return installCopilotCliBundle(context);
    case "claude-code":
      return installClaudeCodeBundle(context);
    case "codex":
      return installCodexBundle(context);
  }
}

async function installCursorBundle(
  _bundle: CompiledHarnessBundle,
): Promise<Phase1InstallResult> {
  return {
    state: "installed",
    reason: "Compiled .cursor/ tree is the installed surface for Cursor.",
    nextSteps: [],
  };
}

async function installCopilotCliBundle(
  context: SelectedInstallContext,
): Promise<Phase1InstallResult> {
  const copilotPath = await context.findCommand("copilot");
  const installCommand = `copilot plugin install ${shellQuote(
    context.bundle.outputRoot,
  )}`;

  if (copilotPath === null) {
    return {
      state: "failed",
      reason:
        'GitHub Copilot CLI requires the "copilot" command on PATH to finish installation.',
      nextSteps: [`Install GitHub Copilot CLI, then run ${installCommand}.`],
    };
  }

  try {
    await context.executeCommand(
      copilotPath,
      ["plugin", "install", context.bundle.outputRoot],
      path.dirname(context.bundle.outputRoot),
    );
    return {
      state: "installed",
      reason: `Installed the compiled bundle with ${installCommand}.`,
      nextSteps: [],
    };
  } catch (error) {
    return {
      state: "failed",
      reason: `copilot plugin install failed: ${commandFailureMessage(error)}`,
      nextSteps: [],
    };
  }
}

async function installClaudeCodeBundle(
  context: SelectedInstallContext,
): Promise<Phase1InstallResult> {
  const details = await writeClaudeMarketplace(
    context.bundle.outputRoot,
    context.bundle.pluginMetadata,
  );
  const claudePath = await context.findCommand("claude");
  const addCommand = `claude plugin marketplace add ${shellQuote(
    context.bundle.outputRoot,
  )}`;
  const reason =
    claudePath === null
      ? 'Claude Code still requires manual installation, and the "claude" CLI is not on PATH for the marketplace-add step.'
      : "Claude Code still requires manual installation after adding the local marketplace.";

  return {
    state: "manual",
    reason,
    nextSteps: [
      addCommand,
      `Open Claude Code, run /plugin, then install "${details.pluginName}" from "${details.marketplaceName}".`,
    ],
  };
}

async function installCodexBundle(
  context: SelectedInstallContext,
): Promise<Phase1InstallResult> {
  const details = await writeCodexMarketplace(
    context.bundle.outputRoot,
    context.bundle.pluginMetadata,
  );
  const codexPath = await context.findCommand("codex");
  const addCommand = `codex plugin marketplace add ${shellQuote(
    context.bundle.outputRoot,
  )}`;
  const reason =
    codexPath === null
      ? 'Codex still requires manual installation, and the "codex" CLI is not on PATH for the marketplace-add step.'
      : "Codex still requires manual installation after adding the local marketplace.";

  return {
    state: "manual",
    reason,
    nextSteps: [
      addCommand,
      "Restart Codex.",
      `Open /plugins, choose "${details.marketplaceName}", and install "${details.pluginName}".`,
    ],
  };
}
