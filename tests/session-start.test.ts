import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  checkForUpdate,
  recordNudgedVersion,
  runSessionStart,
  shouldCheckUpdate,
} from "../src/lib/session-start.js";

const execFileAsync = promisify(execFile);

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map(async (dir) => {
      await rm(dir, { recursive: true, force: true });
    }),
  );
});

async function makeHome(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "session-start-home-"));
  tempDirs.push(dir);
  return dir;
}

async function makeRepo(): Promise<string> {
  const { execFileSync } = await import("node:child_process");
  const cwd = await mkdtemp(path.join(os.tmpdir(), "session-start-repo-"));
  tempDirs.push(cwd);
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
  return cwd;
}

describe("checkForUpdate", () => {
  it("returns behind=true when registry version is newer", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "9.9.9" }),
    });

    const result = await checkForUpdate({
      currentVersion: "0.1.0",
      timeoutMs: 1000,
      fetch: fetchFn as unknown as typeof fetch,
    });

    expect(result).not.toBeNull();
    expect(result?.behind).toBe(true);
    expect(result?.latestVersion).toBe("9.9.9");
  });

  it("returns behind=false when current matches registry", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "0.1.0" }),
    });

    const result = await checkForUpdate({
      currentVersion: "0.1.0",
      timeoutMs: 1000,
      fetch: fetchFn as unknown as typeof fetch,
    });

    expect(result).not.toBeNull();
    expect(result?.behind).toBe(false);
  });

  it("returns null when fetch times out at the configured deadline", async () => {
    const slow = vi.fn(async (_url, init?: { signal?: AbortSignal }) => {
      return await new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const err = new Error("aborted");
          (err as { name?: string }).name = "AbortError";
          reject(err);
        });
      });
    });

    const result = await checkForUpdate({
      currentVersion: "0.1.0",
      timeoutMs: 5,
      fetch: slow as unknown as typeof fetch,
    });

    expect(result).toBeNull();
  });

  it("returns null on non-OK responses", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({}),
    });

    const result = await checkForUpdate({
      currentVersion: "0.1.0",
      timeoutMs: 1000,
      fetch: fetchFn as unknown as typeof fetch,
    });

    expect(result).toBeNull();
  });

  it("returns null when the registry payload has no version field", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ description: "no version here" }),
    });

    const result = await checkForUpdate({
      currentVersion: "0.1.0",
      timeoutMs: 1000,
      fetch: fetchFn as unknown as typeof fetch,
    });

    expect(result).toBeNull();
  });
});

describe("shouldCheckUpdate / recordNudgedVersion", () => {
  it("returns true on first run (no .update-check file)", async () => {
    const home = await makeHome();
    expect(shouldCheckUpdate(home, new Date())).toBe(true);
  });

  it("returns false when last check was within 24h", async () => {
    const home = await makeHome();
    const now = new Date();
    const recent = new Date(now.getTime() - 60 * 60 * 1000); // 1h ago
    await writeFile(
      path.join(home, ".update-check"),
      JSON.stringify({
        checked_at: recent.toISOString(),
        latest_version: "0.1.0",
        nudged_for_version: null,
      }),
      "utf8",
    );

    expect(shouldCheckUpdate(home, now)).toBe(false);
  });

  it("returns true when last check was over 24h ago", async () => {
    const home = await makeHome();
    const now = new Date();
    const stale = new Date(now.getTime() - 25 * 60 * 60 * 1000);
    await writeFile(
      path.join(home, ".update-check"),
      JSON.stringify({
        checked_at: stale.toISOString(),
        latest_version: "0.1.0",
        nudged_for_version: null,
      }),
      "utf8",
    );

    expect(shouldCheckUpdate(home, now)).toBe(true);
  });

  it("recordNudgedVersion suppresses repeats for the same version", async () => {
    const home = await makeHome();
    const now = new Date();
    await recordNudgedVersion(home, "1.2.3", now);
    const data = JSON.parse(
      await readFile(path.join(home, ".update-check"), "utf8"),
    );
    expect(data.nudged_for_version).toBe("1.2.3");
    expect(data.latest_version).toBe("1.2.3");
    expect(data.checked_at).toBe(now.toISOString());
  });

  it("returns true when .update-check is malformed JSON", async () => {
    const home = await makeHome();
    await writeFile(path.join(home, ".update-check"), "not-json{{{", "utf8");

    expect(shouldCheckUpdate(home, new Date())).toBe(true);
  });

  it("returns true when checked_at is missing or non-string", async () => {
    const home = await makeHome();
    await writeFile(
      path.join(home, ".update-check"),
      JSON.stringify({ checked_at: 12345 }),
      "utf8",
    );

    expect(shouldCheckUpdate(home, new Date())).toBe(true);
  });

  it("returns true when checked_at is unparseable", async () => {
    const home = await makeHome();
    await writeFile(
      path.join(home, ".update-check"),
      JSON.stringify({ checked_at: "not-a-date" }),
      "utf8",
    );

    expect(shouldCheckUpdate(home, new Date())).toBe(true);
  });
});

describe("runSessionStart — budget + idempotency", () => {
  it("returns ok=true and ensures the cheese-home tree exists", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      log: () => undefined,
    });

    expect(result.ok).toBe(true);
    const { stat } = await import("node:fs/promises");
    expect((await stat(path.join(home, "projects"))).isDirectory()).toBe(true);
  });

  it("skips sweep + update-check when maxTimeMs is below the per-phase floor", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    const fetchFn = vi.fn();

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 1, // below sweep + update floors
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log: () => undefined,
    });

    expect(result.ok).toBe(true);
    expect(result.sweptReport).toBeUndefined();
    expect(result.updateNudge).toBeUndefined();
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("logs reap summary when sweep reports reaped entries (non-quiet)", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    // Pre-create a stale milknado db inside cheese-home so the sweep finds it.
    const fs = await import("node:fs/promises");
    const projectsDir = path.join(home, "projects");
    await fs.mkdir(projectsDir, { recursive: true });
    const realCwd = await fs.realpath(cwd);
    const slug = realCwd.replaceAll("/", "-");
    const milknadoDir = path.join(projectsDir, slug, "milknado");
    await fs.mkdir(milknadoDir, { recursive: true });
    const db = path.join(milknadoDir, "milknado.db");
    await fs.writeFile(db, "stale", "utf8");
    const ninetyDaysAgo = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
    await fs.utimes(db, ninetyDaysAgo, ninetyDaysAgo);

    const log = vi.fn();
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "0.1.0" }),
    });

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log,
    });

    expect(result.sweptReport?.reaped.length).toBeGreaterThanOrEqual(1);
    const sweptLogs = log.mock.calls.filter((c) =>
      String(c[0] ?? "").includes("swept"),
    );
    expect(sweptLogs.length).toBeGreaterThanOrEqual(1);
  });

  it("suppresses log output when quiet=true (still records the swept report)", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    const log = vi.fn();
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "9.9.9" }),
    });

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log,
      quiet: true,
    });

    expect(result.updateNudge?.version).toBe("9.9.9");
    const nudgeLogs = log.mock.calls.filter((c) =>
      String(c[0] ?? "").includes("9.9.9"),
    );
    expect(nudgeLogs).toEqual([]);
  });

  it("records the check timestamp even when there is no nudge to fire", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "0.1.0" }), // current matches latest
    });

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log: () => undefined,
    });

    expect(result.updateNudge).toBeUndefined();
    const fs = await import("node:fs/promises");
    const data = JSON.parse(
      await fs.readFile(path.join(home, ".update-check"), "utf8"),
    );
    expect(data.latest_version).toBe("0.1.0");
    expect(typeof data.checked_at).toBe("string");
  });

  it("handles a .update-check file with non-string nudged_for_version (treated as null)", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    // Pre-write a malformed-but-parseable .update-check from a prior session.
    const stale = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString();
    await writeFile(
      path.join(home, ".update-check"),
      JSON.stringify({
        checked_at: stale,
        latest_version: 12345, // wrong type, must be ignored
        nudged_for_version: false, // wrong type, treated as null
      }),
      "utf8",
    );
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "9.9.9" }),
    });

    const result = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log: () => undefined,
    });

    expect(result.updateNudge?.version).toBe("9.9.9");
  });

  it("suppresses repeat nudges for the same version", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    const log = vi.fn();
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "9.9.9" }),
    });

    const first = await runSessionStart({
      cwd,
      home,
      now: new Date(),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log,
    });
    expect(first.updateNudge?.version).toBe("9.9.9");
    const initialNudgeLogs = log.mock.calls.filter((c) =>
      String(c[0] ?? "").includes("9.9.9"),
    ).length;
    expect(initialNudgeLogs).toBeGreaterThanOrEqual(1);

    log.mockClear();
    const second = await runSessionStart({
      cwd,
      home,
      now: new Date(Date.now() + 25 * 60 * 60 * 1000),
      maxTimeMs: 5000,
      currentVersion: "0.1.0",
      fetch: fetchFn as unknown as typeof fetch,
      log,
    });

    expect(second.updateNudge).toBeUndefined();
    const repeatNudgeLogs = log.mock.calls.filter((c) =>
      String(c[0] ?? "").includes("9.9.9"),
    ).length;
    expect(repeatNudgeLogs).toBe(0);
  });
});

describe("session-start CLI", () => {
  it("uses the default stdout log when no log option is provided", async () => {
    const cwd = await makeRepo();
    const home = await makeHome();
    const fs = await import("node:fs/promises");
    const projectsDir = path.join(home, "projects");
    await fs.mkdir(projectsDir, { recursive: true });
    const realCwd = await fs.realpath(cwd);
    const slug = realCwd.replaceAll("/", "-");
    const milknadoDir = path.join(projectsDir, slug, "milknado");
    await fs.mkdir(milknadoDir, { recursive: true });
    const db = path.join(milknadoDir, "milknado.db");
    await fs.writeFile(db, "stale", "utf8");
    const ninetyDaysAgo = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
    await fs.utimes(db, ninetyDaysAgo, ninetyDaysAgo);

    const writes: string[] = [];
    const original = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((chunk: unknown) => {
      writes.push(String(chunk));
      return true;
    }) as typeof process.stdout.write;
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: "0.1.0" }),
    });

    try {
      await runSessionStart({
        cwd,
        home,
        now: new Date(),
        maxTimeMs: 5000,
        currentVersion: "0.1.0",
        fetch: fetchFn as unknown as typeof fetch,
      });
    } finally {
      process.stdout.write = original;
    }

    const sweptWrite = writes.find((w) => w.includes("swept"));
    expect(sweptWrite).toBeDefined();
  });

  it("registers the session-start subcommand and prints help text", async () => {
    const { stdout } = await execFileAsync(
      "npx",
      ["tsx", "src/index.ts", "session-start", "--help"],
      { cwd: path.resolve(".") },
    );

    expect(stdout).toContain("session-start");
    expect(stdout).toContain("--root");
    expect(stdout).toContain("--quiet");
    expect(stdout).toContain("--max-time");
  });
});
