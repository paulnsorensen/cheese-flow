import { type SpawnOptionsWithoutStdio, spawn } from "node:child_process";
import path from "node:path";

type OutputChunk = string | Uint8Array;

export type OutputWriter = {
  write(chunk: OutputChunk): unknown;
};

type OutputReader = {
  on(event: "data", listener: (chunk: OutputChunk) => void): unknown;
};

export type SpawnedProcess = {
  stdout: OutputReader;
  stderr: OutputReader;
  on(event: "close", listener: (code: number | null) => void): unknown;
  on(event: "error", listener: (error: unknown) => void): unknown;
};

export type SpawnFn = (
  file: string,
  args: readonly string[],
  options: SpawnOptionsWithoutStdio,
) => SpawnedProcess;

export type RunMilknadoCommandOptions = {
  projectRoot: string;
  spawnFn?: SpawnFn;
  stdout?: OutputWriter;
  stderr?: OutputWriter;
};

const spawnProcess: SpawnFn = (file, args, options) =>
  spawn(file, args, options);

export function getMilknadoBackendScriptPath(projectRoot: string): string {
  return path.join(projectRoot, "python", "milknado.py");
}

export function getMilknadoCommand(projectRoot: string): {
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
      getMilknadoBackendScriptPath(projectRoot),
    ],
  };
}

export async function runMilknadoCommand(
  options: RunMilknadoCommandOptions,
): Promise<void> {
  const spawnFn = options.spawnFn ?? spawnProcess;
  const stdout = options.stdout ?? process.stdout;
  const stderr = options.stderr ?? process.stderr;
  const { command, args } = getMilknadoCommand(options.projectRoot);
  const child = spawnFn(command, args, {
    cwd: options.projectRoot,
    stdio: "pipe",
  });

  child.stdout.on("data", (chunk: OutputChunk) => {
    stdout.write(chunk);
  });
  child.stderr.on("data", (chunk: OutputChunk) => {
    stderr.write(chunk);
  });

  await waitForExit(child);
}

async function waitForExit(child: SpawnedProcess): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    let settled = false;

    const settle = (callback: () => void) => {
      if (settled) {
        return;
      }

      settled = true;
      callback();
    };

    child.on("error", (error: unknown) => {
      settle(() => {
        if (isMissingExecutableError(error)) {
          reject(
            new Error(
              'Unable to run milknado because "uv" was not found on PATH. Install uv from https://docs.astral.sh/uv/.',
            ),
          );
          return;
        }

        const message = error instanceof Error ? error.message : String(error);
        reject(new Error(`milknado backend failed via uv: ${message}`));
      });
    });

    child.on("close", (code: number | null) => {
      settle(() => {
        if (code === 0) {
          resolve();
          return;
        }

        reject(
          new Error(
            `milknado backend failed via uv with exit code ${code ?? "unknown"}.`,
          ),
        );
      });
    });
  });
}

function isMissingExecutableError(
  error: unknown,
): error is NodeJS.ErrnoException {
  return isErrnoException(error) && error.code === "ENOENT";
}

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}
