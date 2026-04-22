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
  execFileFn?: ExecFileFn;
  stdout?: Pick<Writable, "write">;
  stderr?: Pick<Writable, "write">;
};

const execFileAsync = promisify(execFile) as ExecFileFn;

export function getMilknadoBackendScriptPath(projectRoot: string): string {
  return path.join(projectRoot, "python", "milknado.py");
}

export async function runMilknadoCommand(
  options: RunMilknadoCommandOptions,
): Promise<void> {
  const execFileFn = options.execFileFn ?? execFileAsync;
  const stdout = options.stdout ?? process.stdout;
  const stderr = options.stderr ?? process.stderr;
  const backendScriptPath = getMilknadoBackendScriptPath(options.projectRoot);

  try {
    const { stdout: output, stderr: errorOutput } = await execFileFn(
      "uv",
      ["run", "--project", options.projectRoot, "python", backendScriptPath],
      {
        cwd: options.projectRoot,
        encoding: "utf8",
      },
    );

    if (output.length > 0) {
      stdout.write(output);
    }
    if (errorOutput.length > 0) {
      stderr.write(errorOutput);
    }
  } catch (error) {
    writeKnownOutput(stdout, stderr, error);

    if (isMissingExecutableError(error)) {
      throw new Error(
        'Unable to run milknado because "uv" was not found on PATH. Install uv from https://docs.astral.sh/uv/.',
      );
    }

    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`milknado backend failed via uv: ${message}`);
  }
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
