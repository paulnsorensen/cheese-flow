import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
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

function runScript(cwd: string): {
  code: number;
  stdout: string;
  stderr: string;
} {
  const result = spawnSync("bash", [SCRIPT_PATH], {
    cwd,
    encoding: "utf8",
  });
  return {
    code: result.status ?? -1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
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
});
