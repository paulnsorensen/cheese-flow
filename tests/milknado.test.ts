import { execFile, execFileSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getMilknadoBackendScriptPath,
  getMilknadoCommand,
  runMilknadoCommand,
  type SpawnFn,
} from "../src/lib/milknado.js";

const execFileAsync = promisify(execFile);

function makeFixturePaths(dbPath: string) {
  return {
    root: path.dirname(path.dirname(path.dirname(path.dirname(dbPath)))),
    projectDir: path.dirname(path.dirname(dbPath)),
    milknadoDb: dbPath,
    worktreeDir: path.join(
      path.dirname(path.dirname(dbPath)),
      "worktrees",
      "fixture",
    ),
    manifestsDir: "",
    runsDir: "",
    sharedDir: "",
  };
}

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map(async (d) => {
      await rm(d, { recursive: true, force: true });
    }),
  );
});

describe("milknado helpers", () => {
  it("builds the backend path relative to the project root", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");

    expect(getMilknadoBackendScriptPath(projectRoot)).toBe(
      path.join(projectRoot, "python", "milknado.py"),
    );
  });

  it("builds the uv command for the backend, appending --db-path from a CheeseHomePaths", () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");
    const dbPath = path.resolve(
      path.sep,
      "tmp",
      "cheese-home-fixture",
      "projects",
      "-tmp-cheese-flow",
      "milknado",
      "milknado.db",
    );

    const cmd = getMilknadoCommand(projectRoot, {
      cheeseHomePaths: {
        root: path.resolve(path.sep, "tmp", "cheese-home-fixture"),
        projectDir: path.resolve(
          path.sep,
          "tmp",
          "cheese-home-fixture",
          "projects",
          "-tmp-cheese-flow",
        ),
        milknadoDb: dbPath,
        worktreeDir: path.resolve(
          path.sep,
          "tmp",
          "cheese-home-fixture",
          "projects",
          "-tmp-cheese-flow",
          "worktrees",
          "-tmp-cheese-flow",
        ),
        manifestsDir: "",
        runsDir: "",
        sharedDir: "",
      },
    });

    expect(cmd).toEqual({
      command: "uv",
      args: [
        "run",
        "--project",
        projectRoot,
        "python",
        path.join(projectRoot, "python", "milknado.py"),
        "--db-path",
        dbPath,
      ],
      env: { MILKNADO_DB_PATH: dbPath },
    });
  });

  it("falls back to resolveCheeseHome when cheeseHomePaths is omitted", async () => {
    const projectRoot = await mkdtemp(
      path.join(os.tmpdir(), "milknado-resolve-"),
    );
    tempDirs.push(projectRoot);
    execFileSync("git", ["init", "--quiet", "-b", "main", projectRoot]);
    execFileSync(
      "git",
      ["-C", projectRoot, "commit", "--allow-empty", "-m", "init", "--quiet"],
      {
        env: {
          ...process.env,
          GIT_AUTHOR_NAME: "Test",
          GIT_AUTHOR_EMAIL: "test@example.com",
          GIT_COMMITTER_NAME: "Test",
          GIT_COMMITTER_EMAIL: "test@example.com",
        },
      },
    );

    const cmd = getMilknadoCommand(projectRoot);

    expect(cmd.command).toBe("uv");
    expect(cmd.args).toContain("--db-path");
    const dbPath = cmd.args[cmd.args.indexOf("--db-path") + 1];
    expect(dbPath).toBeDefined();
    expect(dbPath?.endsWith(path.join("milknado", "milknado.db"))).toBe(true);
    expect(cmd.env.MILKNADO_DB_PATH).toBe(dbPath);
  });

  it("runs the backend via uv, sets MILKNADO_DB_PATH env, and streams stdout and stderr", async () => {
    const projectRoot = path.resolve(path.sep, "tmp", "cheese-flow");
    const dbPath = path.resolve(path.sep, "tmp", "cheese-home", "milknado.db");
    const stdout = vi.fn();
    const stderr = vi.fn();
    const child = createMockChildProcess();
    const spawnFn = vi.fn<SpawnFn>().mockReturnValue(child);

    const runPromise = runMilknadoCommand({
      projectRoot,
      cheeseHomePaths: makeFixturePaths(dbPath),
      spawnFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(spawnFn).toHaveBeenCalledTimes(1);
    const callArgs = spawnFn.mock.calls[0];
    expect(callArgs?.[0]).toBe("uv");
    expect(callArgs?.[1]).toEqual([
      "run",
      "--project",
      projectRoot,
      "python",
      path.join(projectRoot, "python", "milknado.py"),
      "--db-path",
      dbPath,
    ]);
    const spawnOpts = callArgs?.[2] as
      | { cwd?: string; stdio?: string; env?: Record<string, string> }
      | undefined;
    expect(spawnOpts?.cwd).toBe(projectRoot);
    expect(spawnOpts?.stdio).toBe("pipe");
    expect(spawnOpts?.env?.MILKNADO_DB_PATH).toBe(dbPath);

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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
      cheeseHomePaths: makeFixturePaths(
        path.resolve(path.sep, "tmp", "cheese-home", "milknado.db"),
      ),
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
