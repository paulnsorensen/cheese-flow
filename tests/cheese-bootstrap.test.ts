import { spawnSync } from "node:child_process";
import {
  mkdir,
  mkdtemp,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const SCRIPT_PATH = path.join(REPO_ROOT, "hooks", "cheese-bootstrap.sh");

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map(async (dir) => {
      await rm(dir, { recursive: true, force: true });
    }),
  );
});

async function makeTempCwd(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cheese-bootstrap-"));
  tempDirs.push(dir);
  return dir;
}

function runScript(
  cwd: string,
  pathOverride?: string,
): {
  code: number;
  stdout: string;
  stderr: string;
} {
  const result = spawnSync("bash", [SCRIPT_PATH], {
    cwd,
    encoding: "utf8",
    env: pathOverride ? { ...process.env, PATH: pathOverride } : process.env,
  });
  return {
    code: result.status ?? -1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

async function makeShimDir(body: string): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cheese-shim-"));
  tempDirs.push(dir);
  const shim = path.join(dir, "cheese");
  await writeFile(shim, body, "utf8");
  await import("node:fs/promises").then((m) => m.chmod(shim, 0o755));
  return dir;
}

describe("AC5: hooks/cheese-bootstrap.sh idempotent bootstrap", () => {
  it("creates .cheese/ and adds .cheese/ exactly once when run twice", async () => {
    const cwd = await makeTempCwd();
    await writeFile(
      path.join(cwd, ".gitignore"),
      "node_modules/\ndist/\n",
      "utf8",
    );

    const first = runScript(cwd);
    expect(first.code, `first run stderr: ${first.stderr}`).toBe(0);

    const second = runScript(cwd);
    expect(second.code, `second run stderr: ${second.stderr}`).toBe(0);

    const cheeseStat = await stat(path.join(cwd, ".cheese"));
    expect(cheeseStat.isDirectory()).toBe(true);

    const gitignore = await readFile(path.join(cwd, ".gitignore"), "utf8");
    const matchingLines = gitignore
      .split(/\r?\n/)
      .filter((line: string) => line === ".cheese/");
    expect(matchingLines).toHaveLength(1);
  });

  it("creates .gitignore containing .cheese/ when .gitignore is missing", async () => {
    const cwd = await makeTempCwd();

    const result = runScript(cwd);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const cheeseStat = await stat(path.join(cwd, ".cheese"));
    expect(cheeseStat.isDirectory()).toBe(true);

    const gitignore = await readFile(path.join(cwd, ".gitignore"), "utf8");
    const matchingLines = gitignore
      .split(/\r?\n/)
      .filter((line: string) => line === ".cheese/");
    expect(matchingLines).toHaveLength(1);
  });

  it("preserves existing entries when .gitignore lacks a trailing newline", async () => {
    const cwd = await makeTempCwd();
    await writeFile(
      path.join(cwd, ".gitignore"),
      "node_modules/\ndist/",
      "utf8",
    );

    const result = runScript(cwd);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const lines = (await readFile(path.join(cwd, ".gitignore"), "utf8"))
      .split(/\r?\n/)
      .filter((line: string) => line.length > 0);
    expect(lines).toContain("node_modules/");
    expect(lines).toContain("dist/");
    expect(lines).toContain(".cheese/");
    expect(lines.filter((line: string) => line === ".cheese/")).toHaveLength(1);
  });

  it("writes a single .cheese/ line when .gitignore is empty (zero bytes)", async () => {
    const cwd = await makeTempCwd();
    await writeFile(path.join(cwd, ".gitignore"), "", "utf8");

    const result = runScript(cwd);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const contents = await readFile(path.join(cwd, ".gitignore"), "utf8");
    expect(contents).toBe(".cheese/\n");
  });

  it("preserves existing contents inside a pre-existing .cheese/ directory", async () => {
    const cwd = await makeTempCwd();
    await mkdir(path.join(cwd, ".cheese", "specs"), { recursive: true });
    await writeFile(
      path.join(cwd, ".cheese", "specs", "existing.md"),
      "preserve me",
      "utf8",
    );

    const result = runScript(cwd);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const preserved = await readFile(
      path.join(cwd, ".cheese", "specs", "existing.md"),
      "utf8",
    );
    expect(preserved).toBe("preserve me");
  });

  it("treats .cheese (no trailing slash) as distinct and still appends .cheese/", async () => {
    const cwd = await makeTempCwd();
    await writeFile(path.join(cwd, ".gitignore"), ".cheese\n", "utf8");

    const result = runScript(cwd);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const lines = (await readFile(path.join(cwd, ".gitignore"), "utf8"))
      .split(/\r?\n/)
      .filter((line: string) => line.length > 0);
    expect(lines).toEqual([".cheese", ".cheese/"]);
  });
});

describe("hooks/cheese-bootstrap.sh — CLI handoff (R5)", () => {
  it("exits 0 when cheese is not on PATH (PR #31 behavior preserved)", async () => {
    const cwd = await makeTempCwd();
    // Empty dir prepended to a minimal coreutils PATH — proves the
    // `command -v cheese` short-circuit fires without breaking mkdir/grep/tail.
    const empty = await mkdtemp(path.join(os.tmpdir(), "cheese-empty-path-"));
    tempDirs.push(empty);

    const result = runScript(cwd, `${empty}:/usr/bin:/bin`);

    expect(result.code, `stderr: ${result.stderr}`).toBe(0);
    const cheeseStat = await stat(path.join(cwd, ".cheese"));
    expect(cheeseStat.isDirectory()).toBe(true);
  });

  it("invokes 'cheese session-start' when present and continues on non-zero exit", async () => {
    const cwd = await makeTempCwd();
    const callLog = path.join(cwd, "cheese-call.log");
    const shimDir = await makeShimDir(
      `#!/usr/bin/env bash\nprintf '%s\\n' "$@" > ${JSON.stringify(callLog)}\nexit 7\n`,
    );
    const newPath = `${shimDir}:${process.env.PATH ?? ""}`;

    const result = runScript(cwd, newPath);

    // Hook must NOT propagate the non-zero exit from the CLI handoff.
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const recorded = await readFile(callLog, "utf8");
    expect(recorded).toContain("session-start");
    expect(recorded).toContain("--quiet");
    expect(recorded).toContain("--max-time");
  });

  it("invokes 'cheese session-start --root <pwd>' with the worktree path", async () => {
    const cwd = await makeTempCwd();
    const callLog = path.join(cwd, "cheese-call.log");
    const shimDir = await makeShimDir(
      `#!/usr/bin/env bash\nprintf '%s\\n' "$@" > ${JSON.stringify(callLog)}\nexit 0\n`,
    );
    const newPath = `${shimDir}:${process.env.PATH ?? ""}`;

    const result = runScript(cwd, newPath);
    expect(result.code, `stderr: ${result.stderr}`).toBe(0);

    const recorded = await readFile(callLog, "utf8");
    expect(recorded).toContain("--root");
    // Resolve symlinks (macOS /tmp -> /private/tmp); shim records pwd which may be either.
    const fs = await import("node:fs/promises");
    const realCwd = await fs.realpath(cwd);
    expect(recorded.includes(cwd) || recorded.includes(realCwd)).toBe(true);
  });
});
