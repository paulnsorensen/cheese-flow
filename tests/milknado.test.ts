import { execFile } from "node:child_process";
import { EventEmitter } from "node:events";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it, vi } from "vitest";
import {
  getMilknadoBackendScriptPath,
  getMilknadoCommand,
  runMilknadoCommand,
  type SpawnFn,
} from "../src/lib/milknado.js";

const execFileAsync = promisify(execFile);

describe("milknado helpers", () => {
  it("builds the backend path relative to the project root", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");

    expect(getMilknadoBackendScriptPath(projectRoot)).toBe(
      path.join(projectRoot, "python", "milknado.py"),
    );
  });

  it("builds the uv command for the backend", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");

    expect(getMilknadoCommand(projectRoot)).toEqual({
      command: "uv",
      args: [
        "run",
        "--project",
        projectRoot,
        "python",
        path.join(projectRoot, "python", "milknado.py"),
      ],
    });
  });

  it("runs the backend via uv and streams stdout and stderr", async () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");
    const stdout = vi.fn();
    const stderr = vi.fn();
    const child = createMockChildProcess();
    const spawnFn = vi.fn<SpawnFn>().mockReturnValue(child);

    const runPromise = runMilknadoCommand({
      projectRoot,
      spawnFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(spawnFn).toHaveBeenCalledWith(
      "uv",
      [
        "run",
        "--project",
        projectRoot,
        "python",
        path.join(projectRoot, "python", "milknado.py"),
      ],
      {
        cwd: projectRoot,
        stdio: "pipe",
      },
    );

    child.stdout.emit("data", "Milknado ready\n");
    child.stderr.emit("data", "warning\n");
    child.emit("close", 0);

    await expect(runPromise).resolves.toBeUndefined();
    expect(stdout).toHaveBeenCalledWith("Milknado ready\n");
    expect(stderr).toHaveBeenCalledWith("warning\n");
  });

  it("fails clearly when uv is unavailable", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit(
      "error",
      Object.assign(new Error("missing"), { code: "ENOENT" }),
    );

    await expect(runPromise).rejects.toThrow(/Install uv/u);
  });

  it("surfaces spawn errors from uv", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("error", new Error("boom"));

    await expect(runPromise).rejects.toThrow(
      /milknado backend failed via uv: boom/u,
    );
  });

  it("surfaces non-zero exit codes after streaming output", async () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");
    const stdout = vi.fn();
    const stderr = vi.fn();
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot,
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    child.stdout.emit("data", "partial\n");
    child.stderr.emit("data", "traceback\n");
    child.emit("close", 1);

    await expect(runPromise).rejects.toThrow(
      /milknado backend failed via uv with exit code 1\./u,
    );
    expect(stdout).toHaveBeenCalledWith("partial\n");
    expect(stderr).toHaveBeenCalledWith("traceback\n");
  });

  it("reports an unknown exit code when the process closes without one", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("close", null, null);

    await expect(runPromise).rejects.toThrow(
      /milknado backend failed via uv with exit code unknown\./u,
    );
  });

  it("reports the terminating signal when the process is killed", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("close", null, "SIGKILL");

    await expect(runPromise).rejects.toThrow(
      /milknado backend failed via uv with signal SIGKILL\./u,
    );
  });

  it("treats SIGINT as a user-cancelled run", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("close", null, "SIGINT");

    await expect(runPromise).rejects.toThrow(
      /milknado run cancelled by SIGINT\./u,
    );
  });

  it("treats SIGTERM as a user-cancelled run", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("close", null, "SIGTERM");

    await expect(runPromise).rejects.toThrow(
      /milknado run cancelled by SIGTERM\./u,
    );
  });

  it("ignores later process events after the command has already settled", async () => {
    const child = createMockChildProcess();
    const runPromise = runMilknadoCommand({
      projectRoot: path.resolve(path.sep, "tmp", "cheese-flow"),
      spawnFn: vi.fn<SpawnFn>().mockReturnValue(child),
    });

    child.emit("close", 0);
    child.emit("error", new Error("late failure"));

    await expect(runPromise).resolves.toBeUndefined();
  });
});

describe("milknado CLI", () => {
  it("wires up milknado help without requiring uv or Python", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "milknado", "--help"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain("milknado");
    expect(stdout).toContain("Usage:");
    expect(stdout).toContain(
      "Project root that contains ./python and pyproject.toml.",
    );
  });
});

function createMockChildProcess() {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
  };

  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();

  return child;
}
