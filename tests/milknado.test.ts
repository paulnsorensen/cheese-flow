import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it, vi } from "vitest";
import {
  type ExecFileFn,
  getMilknadoBackendScriptPath,
  runMilknadoCommand,
} from "../src/lib/milknado.js";

const execFileAsync = promisify(execFile);

describe("milknado helpers", () => {
  it("builds a backend path relative to the project root", () => {
    expect(getMilknadoBackendScriptPath("/tmp/cheese-flow")).toBe(
      "/tmp/cheese-flow/python/milknado.py",
    );
  });

  it("runs the backend via uv", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi.fn<ExecFileFn>().mockResolvedValue({
      stdout: "Milknado ready\n",
      stderr: "",
    });

    await runMilknadoCommand({
      projectRoot: "/tmp/cheese-flow",
      execFileFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(execFileFn).toHaveBeenCalledWith(
      "uv",
      [
        "run",
        "--project",
        "/tmp/cheese-flow",
        "python",
        "/tmp/cheese-flow/python/milknado.py",
      ],
      {
        cwd: "/tmp/cheese-flow",
        encoding: "utf8",
      },
    );
    expect(stdout).toHaveBeenCalledWith("Milknado ready\n");
    expect(stderr).not.toHaveBeenCalled();
  });

  it("fails clearly when uv is unavailable", async () => {
    const execFileFn = vi
      .fn<ExecFileFn>()
      .mockRejectedValue(
        Object.assign(new Error("missing"), { code: "ENOENT" }),
      );

    await expect(
      runMilknadoCommand({
        projectRoot: "/tmp/cheese-flow",
        execFileFn,
      }),
    ).rejects.toThrow(/Install uv/u);
  });

  it("writes stderr from a successful backend run", async () => {
    const stdout = vi.fn();
    const stderr = vi.fn();
    const execFileFn = vi.fn<ExecFileFn>().mockResolvedValue({
      stdout: "",
      stderr: "warning\n",
    });

    await runMilknadoCommand({
      projectRoot: "/tmp/cheese-flow",
      execFileFn,
      stdout: { write: stdout },
      stderr: { write: stderr },
    });

    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).toHaveBeenCalledWith("warning\n");
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
        execFileFn,
        stdout: { write: stdout },
        stderr: { write: stderr },
      }),
    ).rejects.toThrow(/milknado backend failed via uv/u);
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
        execFileFn,
        stdout: { write: stdout },
        stderr: { write: stderr },
      }),
    ).rejects.toThrow(/milknado backend failed via uv: boom/u);
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });
});

describe("milknado CLI", () => {
  it("runs the shipped Python backend, rich UI, and OR-Tools solver", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "milknado"],
      {
        cwd: path.resolve("."),
      },
    );

    expect(stdout).toContain("Milknado");
    expect(stdout).toContain("rich TUI + OR-Tools");
    expect(stdout).toContain("Linear solver status");
    expect(stdout).toContain("Objective");
  });
});
