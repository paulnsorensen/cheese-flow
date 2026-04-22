import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it, vi } from "vitest";
import {
  type ExecFileFn,
  getMilknadoBackendScriptPath,
  getPythonCandidates,
  runMilknadoCommand,
} from "../src/lib/milknado.js";

const execFileAsync = promisify(execFile);

describe("milknado helpers", () => {
  it("builds a backend path relative to the project root", () => {
    expect(getMilknadoBackendScriptPath("/tmp/cheese-flow")).toBe(
      "/tmp/cheese-flow/python/milknado.py",
    );
  });

  it("prefers a configured Python binary without duplicating fallbacks", () => {
    expect(
      getPythonCandidates({
        MILKNADO_PYTHON: "python3",
      }),
    ).toEqual(["python3", "python"]);
  });

  it("falls back to the next Python runtime when the first one is missing", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi
      .fn<ExecFileFn>()
      .mockRejectedValueOnce(
        Object.assign(new Error("missing"), { code: "ENOENT" }),
      )
      .mockResolvedValueOnce({
        stdout: "Milknado ready\n",
        stderr: "",
      });

    const command = await runMilknadoCommand({
      projectRoot: "/tmp/cheese-flow",
      env: {
        MILKNADO_PYTHON: "python3",
      },
      execFileFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(command).toBe("python");
    expect(execFileFn).toHaveBeenNthCalledWith(
      1,
      "python3",
      ["/tmp/cheese-flow/python/milknado.py"],
      {
        cwd: "/tmp/cheese-flow",
        encoding: "utf8",
      },
    );
    expect(execFileFn).toHaveBeenNthCalledWith(
      2,
      "python",
      ["/tmp/cheese-flow/python/milknado.py"],
      {
        cwd: "/tmp/cheese-flow",
        encoding: "utf8",
      },
    );
    expect(stdout).toHaveBeenCalledWith("Milknado ready\n");
    expect(stderr).not.toHaveBeenCalled();
  });

  it("writes stderr from a successful backend run", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi.fn<ExecFileFn>().mockResolvedValue({
      stdout: "",
      stderr: "warning\n",
    });

    const command = await runMilknadoCommand({
      projectRoot: "/tmp/cheese-flow",
      execFileFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(command).toBe("python3");
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).toHaveBeenCalledWith("warning\n");
  });

  it("fails clearly when no Python runtime is available", async () => {
    const execFileFn = vi
      .fn<ExecFileFn>()
      .mockRejectedValue(
        Object.assign(new Error("missing"), { code: "ENOENT" }),
      );

    await expect(
      runMilknadoCommand({
        projectRoot: "/tmp/cheese-flow",
        env: {
          MILKNADO_PYTHON: "py",
        },
        execFileFn,
      }),
    ).rejects.toThrow(
      /Unable to find a Python runtime for milknado. Tried: py, python3, python\./u,
    );
    expect(execFileFn).toHaveBeenCalledTimes(3);
  });

  it("surfaces backend failures after writing known output", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi.fn<ExecFileFn>().mockRejectedValue(
      Object.assign(new Error("python exploded"), {
        stdout: "partial\n",
        stderr: "traceback\n",
      }),
    );

    await expect(
      runMilknadoCommand({
        projectRoot: "/tmp/cheese-flow",
        env: {
          MILKNADO_PYTHON: "python3",
        },
        execFileFn,
        stdout: { write: stdout },
        stderr: { write: stderr },
      }),
    ).rejects.toThrow(/milknado backend failed using "python3"/u);
    expect(stdout).toHaveBeenCalledWith("partial\n");
    expect(stderr).toHaveBeenCalledWith("traceback\n");
  });

  it("surfaces non-error backend failures without writing output", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi.fn<ExecFileFn>().mockRejectedValue("boom");

    await expect(
      runMilknadoCommand({
        projectRoot: "/tmp/cheese-flow",
        env: {
          MILKNADO_PYTHON: "python3",
        },
        execFileFn,
        stdout: { write: stdout },
        stderr: { write: stderr },
      }),
    ).rejects.toThrow(/milknado backend failed using "python3": boom/u);
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });
});

describe("milknado CLI", () => {
  it("runs the shipped Python backend and prints its TUI", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "milknado"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain("Milknado");
    expect(stdout).toContain("backend   │ python");
    expect(stdout).toContain("typescript commander");
  });
});
