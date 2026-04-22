import {
  type ExecFileOptionsWithStringEncoding,
  execFile,
} from "node:child_process";
import path from "node:path";
import type { Writable } from "node:stream";
import { promisify } from "node:util";

type ExecFileResult = {
  stdout: string;
  stderr: string;
};

export type ExecFileFn = (
  file: string,
  args: readonly string[],
  options: ExecFileOptionsWithStringEncoding,
) => Promise<ExecFileResult>;

export type RunMilknadoCommandOptions = {
  projectRoot: string;
  env?: NodeJS.ProcessEnv;
  execFileFn?: ExecFileFn;
  stdout?: Pick<Writable, "write">;
  stderr?: Pick<Writable, "write">;
};

const execFileAsync = promisify(execFile) as ExecFileFn;
const defaultPythonCommands = ["python3", "python"] as const;

export function getMilknadoBackendScriptPath(projectRoot: string): string {
  return path.join(projectRoot, "python", "milknado.py");
}

export function getPythonCandidates(
  env: NodeJS.ProcessEnv = process.env,
): string[] {
  const preferred = env.MILKNADO_PYTHON?.trim();
  const candidates = [
    preferred && preferred.length > 0 ? preferred : undefined,
    ...defaultPythonCommands,
  ].filter((value): value is string => Boolean(value));

  return Array.from(new Set(candidates));
}

export async function runMilknadoCommand(
  options: RunMilknadoCommandOptions,
): Promise<string> {
  const execFileFn = options.execFileFn ?? execFileAsync;
  const stdout = options.stdout ?? process.stdout;
  const stderr = options.stderr ?? process.stderr;
  const backendScriptPath = getMilknadoBackendScriptPath(options.projectRoot);
  const candidates = getPythonCandidates(options.env);
  let lastError: unknown;

  for (const candidate of candidates) {
    try {
      const { stdout: output, stderr: errorOutput } = await execFileFn(
        candidate,
        [backendScriptPath],
        {
          cwd: options.projectRoot,
          encoding: "utf8",
        },
      );
      stdout.write(output);
      stderr.write(errorOutput);
      return candidate;
    } catch (error) {
      lastError = error;

      if (isMissingExecutableError(error)) {
        continue;
      }

      writeKnownOutput(stdout, stderr, error);
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(
        `milknado backend failed using "${candidate}": ${message}`,
      );
    }
  }

  const detail =
    isErrnoException(lastError) && typeof lastError.code === "string"
      ? ` (${lastError.code})`
      : "";
  throw new Error(
    `Unable to find a Python runtime for milknado. Tried: ${candidates.join(", ")}${detail}.`,
  );
}

function isMissingExecutableError(
  error: unknown,
): error is NodeJS.ErrnoException {
  return isErrnoException(error) && error.code === "ENOENT";
}

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}

function writeKnownOutput(
  stdout: Pick<Writable, "write">,
  stderr: Pick<Writable, "write">,
  error: unknown,
): void {
  if (typeof error !== "object" || error === null) {
    return;
  }

  if ("stdout" in error && typeof error.stdout === "string") {
    stdout.write(error.stdout);
  }

  if ("stderr" in error && typeof error.stderr === "string") {
    stderr.write(error.stderr);
  }
}
