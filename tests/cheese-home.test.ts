import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  discoverCanonicalRepo,
  ensureCheeseHome,
  parseWorktreeMain,
  pathSlug,
  readRetentionConfig,
  resolveCheeseHome,
} from "../src/lib/cheese-home.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map(async (dir) => {
      await rm(dir, { recursive: true, force: true });
    }),
  );
});

async function makeTempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempDirs.push(dir);
  return dir;
}

describe("pathSlug", () => {
  it("replaces every / with -", () => {
    expect(pathSlug("/Users/paul/Dev/cheese-flow")).toBe(
      "-Users-paul-Dev-cheese-flow",
    );
  });

  it("returns '-' for the filesystem root", () => {
    expect(pathSlug("/")).toBe("-");
  });

  it("preserves a trailing / as a trailing -", () => {
    expect(pathSlug("/Users/paul/Dev/cheese-flow/")).toBe(
      "-Users-paul-Dev-cheese-flow-",
    );
  });

  it("does not escape legitimate '-' in segments (collision is by design)", () => {
    expect(pathSlug("/Users/john-doe/Dev/cheese-flow")).toBe(
      "-Users-john-doe-Dev-cheese-flow",
    );
  });

  it("returns the input unchanged when no / is present", () => {
    expect(pathSlug("plain-name")).toBe("plain-name");
  });
});

describe("discoverCanonicalRepo", () => {
  async function initRealRepo(dir: string): Promise<void> {
    execFileSync("git", ["init", "--quiet", "-b", "main", dir]);
    execFileSync(
      "git",
      ["-C", dir, "commit", "--allow-empty", "-m", "init", "--quiet"],
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
  }

  it("returns the canonical absolute path for a plain checkout", async () => {
    const dir = await makeTempDir("cheese-home-canonical-");
    await initRealRepo(dir);
    const real = await import("node:fs/promises").then((m) => m.realpath(dir));
    expect(discoverCanonicalRepo(dir)).toBe(real);
  });

  it("returns the main worktree path when called from a linked worktree", async () => {
    const main = await makeTempDir("cheese-home-main-");
    await initRealRepo(main);
    const linked = `${main}-linked`;
    tempDirs.push(linked);
    execFileSync("git", [
      "-C",
      main,
      "worktree",
      "add",
      "-b",
      "feature",
      linked,
    ]);

    const realMain = await import("node:fs/promises").then((m) =>
      m.realpath(main),
    );
    expect(discoverCanonicalRepo(linked)).toBe(realMain);
  });

  it("throws when cwd is not inside a git repository", async () => {
    const dir = await makeTempDir("cheese-home-nogit-");
    expect(() => discoverCanonicalRepo(dir)).toThrow(/not inside a git/i);
  });
});

describe("parseWorktreeMain", () => {
  it("returns the path from the first 'worktree <path>' line", () => {
    const out = "worktree /repos/main\nbranch refs/heads/main\nHEAD abc\n";
    expect(parseWorktreeMain(out, "/cwd")).toBe("/repos/main");
  });

  it("throws when the porcelain output is empty", () => {
    expect(() => parseWorktreeMain("", "/cwd")).toThrow(/not inside a git/i);
  });

  it("throws when the first line is not a worktree marker", () => {
    expect(() => parseWorktreeMain("HEAD abc\n", "/cwd")).toThrow(
      /not inside a git/i,
    );
  });
});

describe("resolveCheeseHome — explicit canonicalRepo", () => {
  it("skips git lookup when canonicalRepo is provided", async () => {
    const cwd = await makeTempDir("cheese-home-explicit-cwd-");
    const home = await makeTempDir("cheese-home-explicit-home-");
    const canonicalRepo = "/Users/paul/Dev/example-repo";

    const paths = resolveCheeseHome(cwd, { home, canonicalRepo });

    expect(paths.projectDir).toBe(
      path.join(home, "projects", pathSlug(canonicalRepo)),
    );
  });
});

describe("resolveCheeseHome", () => {
  it("derives all paths from cwd without writing", async () => {
    const cwd = await makeTempDir("cheese-home-resolve-cwd-");
    await execFileSync("git", ["init", "--quiet", "-b", "main", cwd]);
    execFileSync(
      "git",
      ["-C", cwd, "commit", "--allow-empty", "-m", "init", "--quiet"],
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
    const home = await makeTempDir("cheese-home-resolve-home-");

    const paths = resolveCheeseHome(cwd, { home });

    const realCwd = await import("node:fs/promises").then((m) =>
      m.realpath(cwd),
    );
    const repoSlug = pathSlug(realCwd);
    const wtSlug = pathSlug(realCwd);
    expect(paths.root).toBe(home);
    expect(paths.projectDir).toBe(path.join(home, "projects", repoSlug));
    expect(paths.milknadoDb).toBe(
      path.join(home, "projects", repoSlug, "milknado", "milknado.db"),
    );
    expect(paths.worktreeDir).toBe(
      path.join(home, "projects", repoSlug, "worktrees", wtSlug),
    );
    expect(paths.manifestsDir).toBe(
      path.join(home, "projects", repoSlug, "worktrees", wtSlug, "manifests"),
    );
    expect(paths.runsDir).toBe(
      path.join(home, "projects", repoSlug, "worktrees", wtSlug, "runs"),
    );
    expect(paths.sharedDir).toBe(
      path.join(home, "projects", repoSlug, "shared"),
    );

    // No filesystem writes: projects dir must not exist.
    await expect(
      readFile(
        path.join(home, "projects", repoSlug, "milknado", "milknado.db"),
      ),
    ).rejects.toThrow();
  });

  it("uses os.homedir() when no override is given", async () => {
    const cwd = await makeTempDir("cheese-home-resolve-default-");
    execFileSync("git", ["init", "--quiet", "-b", "main", cwd]);
    execFileSync(
      "git",
      ["-C", cwd, "commit", "--allow-empty", "-m", "init", "--quiet"],
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

    const paths = resolveCheeseHome(cwd);
    expect(paths.root).toBe(path.join(os.homedir(), ".cheese"));
  });
});

describe("ensureCheeseHome", () => {
  async function initRepo(cwd: string): Promise<void> {
    execFileSync("git", ["init", "--quiet", "-b", "main", cwd]);
    execFileSync(
      "git",
      ["-C", cwd, "commit", "--allow-empty", "-m", "init", "--quiet"],
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
  }

  it("creates the projectDir tree, manifests/, runs/ and writes a .path sidecar", async () => {
    const cwd = await makeTempDir("cheese-home-ensure-cwd-");
    await initRepo(cwd);
    const home = await makeTempDir("cheese-home-ensure-home-");

    const paths = ensureCheeseHome(cwd, { home });

    const { stat } = await import("node:fs/promises");
    expect((await stat(paths.projectDir)).isDirectory()).toBe(true);
    expect((await stat(path.dirname(paths.milknadoDb))).isDirectory()).toBe(
      true,
    );
    expect((await stat(paths.manifestsDir)).isDirectory()).toBe(true);
    expect((await stat(paths.runsDir)).isDirectory()).toBe(true);
    expect((await stat(paths.sharedDir)).isDirectory()).toBe(true);

    const sidecarPath = path.join(paths.worktreeDir, ".path");
    const sidecar = await readFile(sidecarPath, "utf8");
    const realCwd = await import("node:fs/promises").then((m) =>
      m.realpath(cwd),
    );
    expect(sidecar).toBe(`${realCwd}\n`);
  });

  it("is idempotent: a second call leaves the sidecar pointing at the same path", async () => {
    const cwd = await makeTempDir("cheese-home-ensure-idem-");
    await initRepo(cwd);
    const home = await makeTempDir("cheese-home-ensure-idem-home-");

    const first = ensureCheeseHome(cwd, { home });
    const second = ensureCheeseHome(cwd, { home });

    expect(second.worktreeDir).toBe(first.worktreeDir);
    const sidecar = await readFile(
      path.join(first.worktreeDir, ".path"),
      "utf8",
    );
    const realCwd = await import("node:fs/promises").then((m) =>
      m.realpath(cwd),
    );
    expect(sidecar).toBe(`${realCwd}\n`);
  });
});

describe("readRetentionConfig", () => {
  it("returns the 30-day default when no toml file exists", async () => {
    const projectDir = await makeTempDir("cheese-home-retention-default-");

    const config = readRetentionConfig(projectDir);

    expect(config).toEqual({ defaultDays: 30 });
  });

  it("reads numeric overrides from shared/retention.toml", async () => {
    const projectDir = await makeTempDir("cheese-home-retention-toml-");
    await mkdir(path.join(projectDir, "shared"), { recursive: true });
    await writeFile(
      path.join(projectDir, "shared", "retention.toml"),
      [
        "defaultDays = 14",
        "milknadoDays = 7",
        "manifestsDays = 3",
        "runsDays = 90",
        "worktreeDays = 60",
      ].join("\n"),
      "utf8",
    );

    const config = readRetentionConfig(projectDir);

    expect(config).toEqual({
      defaultDays: 14,
      milknadoDays: 7,
      manifestsDays: 3,
      runsDays: 90,
      worktreeDays: 60,
    });
  });

  it("ignores [section] headers, lines without =, and non-numeric values", async () => {
    const projectDir = await makeTempDir("cheese-home-retention-edge-");
    await mkdir(path.join(projectDir, "shared"), { recursive: true });
    await writeFile(
      path.join(projectDir, "shared", "retention.toml"),
      [
        "[retention]",
        "no-equals-sign-here",
        "milknadoDays = not-a-number",
        "manifestsDays =",
        "runsDays = 12",
      ].join("\n"),
      "utf8",
    );

    const config = readRetentionConfig(projectDir);

    expect(config.defaultDays).toBe(30);
    expect(config.milknadoDays).toBeUndefined();
    expect(config.manifestsDays).toBeUndefined();
    expect(config.runsDays).toBe(12);
  });

  it("ignores comments, blank lines, and unknown keys", async () => {
    const projectDir = await makeTempDir("cheese-home-retention-comments-");
    await mkdir(path.join(projectDir, "shared"), { recursive: true });
    await writeFile(
      path.join(projectDir, "shared", "retention.toml"),
      [
        "# retention overrides",
        "",
        "defaultDays = 21",
        "unknownKey = 99",
        "  milknadoDays = 5  # inline ignored",
      ].join("\n"),
      "utf8",
    );

    const config = readRetentionConfig(projectDir);

    expect(config.defaultDays).toBe(21);
    expect(config.milknadoDays).toBe(5);
    expect(
      (config as unknown as Record<string, unknown>).unknownKey,
    ).toBeUndefined();
  });
});
