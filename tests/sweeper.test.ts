import { mkdir, mkdtemp, rm, stat, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { sweep } from "../src/lib/sweeper.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map(async (dir) => {
      await rm(dir, { recursive: true, force: true });
    }),
  );
});

async function makeHome(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cheese-sweeper-"));
  tempDirs.push(dir);
  await mkdir(path.join(dir, "projects"), { recursive: true });
  return dir;
}

async function setMtime(target: string, daysAgo: number): Promise<void> {
  const when = new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000);
  await utimes(target, when, when);
}

async function createProject(home: string, slug: string): Promise<string> {
  const projectDir = path.join(home, "projects", slug);
  await mkdir(projectDir, { recursive: true });
  await mkdir(path.join(projectDir, "milknado"), { recursive: true });
  await mkdir(path.join(projectDir, "worktrees"), { recursive: true });
  await mkdir(path.join(projectDir, "shared"), { recursive: true });
  return projectDir;
}

describe("sweep — milknado db retention", () => {
  it("reaps milknado.db older than defaultDays", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-repo");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "stale-bytes", "utf8");
    await setMtime(db, 31);

    const report = await sweep({
      scope: "all",
      home,
      now: new Date(),
    });

    expect(report.reaped.map((r) => r.path)).toContain(db);
    await expect(stat(db)).rejects.toThrow();
  });

  it("keeps milknado.db younger than defaultDays", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-fresh");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "fresh", "utf8");
    await setMtime(db, 5);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).not.toContain(db);
    expect((await stat(db)).isFile()).toBe(true);
  });

  it("respects per-repo milknadoDays override", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-override");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "x", "utf8");
    await setMtime(db, 10);
    await writeFile(
      path.join(projectDir, "shared", "retention.toml"),
      "milknadoDays = 7\n",
      "utf8",
    );

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).toContain(db);
  });
});

describe("sweep — manifests + runs retention", () => {
  it("reaps stale worktrees/<slug>/manifests/ but keeps fresh siblings", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-mixed");
    const wtDir = path.join(projectDir, "worktrees", "-Users-paul-mixed");
    await mkdir(path.join(wtDir, "manifests"), { recursive: true });
    await mkdir(path.join(wtDir, "runs", "abc"), { recursive: true });
    await writeFile(path.join(wtDir, ".path"), `${wtDir}\n`, "utf8");
    await setMtime(path.join(wtDir, "manifests"), 40);
    await setMtime(path.join(wtDir, "runs", "abc"), 5);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).toContain(
      path.join(wtDir, "manifests"),
    );
    expect((await stat(path.join(wtDir, "runs", "abc"))).isDirectory()).toBe(
      true,
    );
  });

  it("reaps individual stale run directories under runs/", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-runs");
    const wtDir = path.join(projectDir, "worktrees", "-Users-paul-runs");
    const stale = path.join(wtDir, "runs", "stale");
    const fresh = path.join(wtDir, "runs", "fresh");
    await mkdir(stale, { recursive: true });
    await mkdir(fresh, { recursive: true });
    await writeFile(path.join(wtDir, ".path"), `${wtDir}\n`, "utf8");
    await setMtime(stale, 90);
    await setMtime(fresh, 1);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).toContain(stale);
    expect(report.reaped.map((r) => r.path)).not.toContain(fresh);
  });
});

describe("sweep — whole-worktree reaping", () => {
  it("reaps the whole worktree dir only when stale AND .path target is gone", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-dead");
    const liveDir = await mkdtemp(path.join(os.tmpdir(), "cheese-sweep-live-"));
    tempDirs.push(liveDir);

    const liveSlug = "-Users-paul-live";
    const deadSlug = "-Users-paul-dead-wt";
    const liveWt = path.join(projectDir, "worktrees", liveSlug);
    const deadWt = path.join(projectDir, "worktrees", deadSlug);
    await mkdir(liveWt, { recursive: true });
    await mkdir(deadWt, { recursive: true });
    await writeFile(path.join(liveWt, ".path"), `${liveDir}\n`, "utf8");
    await writeFile(
      path.join(deadWt, ".path"),
      "/tmp/cheese-this-path-should-not-exist-12345\n",
      "utf8",
    );
    // both old enough
    await setMtime(liveWt, 120);
    await setMtime(deadWt, 120);

    const report = await sweep({ scope: "all", home, now: new Date() });

    const reaped = report.reaped.map((r) => r.path);
    expect(reaped).toContain(deadWt);
    expect(reaped).not.toContain(liveWt);
    await expect(stat(deadWt)).rejects.toThrow();
    expect((await stat(liveWt)).isDirectory()).toBe(true);
  });

  it("does not reap a stale worktree if its .path target still exists, even if old", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-stale-but-live");
    const liveDir = await mkdtemp(
      path.join(os.tmpdir(), "cheese-sweep-live2-"),
    );
    tempDirs.push(liveDir);
    const wt = path.join(projectDir, "worktrees", "-Users-paul-stale");
    await mkdir(wt, { recursive: true });
    await writeFile(path.join(wt, ".path"), `${liveDir}\n`, "utf8");
    await setMtime(wt, 120);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).not.toContain(wt);
  });
});

describe("sweep — never reaps in-repo .cheese/", () => {
  it("only walks ~/.cheese/projects, never the user repo", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-isolation");
    // create a stale db so something IS reaped — proves the sweep runs
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "x", "utf8");
    await setMtime(db, 90);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.scannedProjects).toBe(1);
    expect(report.reaped.length).toBeGreaterThanOrEqual(1);
    for (const entry of report.reaped) {
      expect(entry.path.startsWith(home)).toBe(true);
    }
  });
});

describe("sweep — debounce via .last-sweep", () => {
  it("is a no-op when .last-sweep mtime is < 24h ago", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-debounced");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "stale", "utf8");
    await setMtime(db, 90);
    const lastSweep = path.join(home, ".last-sweep");
    await writeFile(lastSweep, "", "utf8");
    await setMtime(lastSweep, 0); // just now

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped).toEqual([]);
    expect(report.scannedProjects).toBe(0);
    expect((await stat(db)).isFile()).toBe(true);
  });

  it("runs and touches .last-sweep when older than 24h", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-due");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "stale", "utf8");
    await setMtime(db, 90);
    const lastSweep = path.join(home, ".last-sweep");
    await writeFile(lastSweep, "", "utf8");
    await setMtime(lastSweep, 2);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.length).toBeGreaterThanOrEqual(1);
    const after = await stat(lastSweep);
    expect(Date.now() - after.mtimeMs).toBeLessThan(60_000);
  });

  it("force=true bypasses the debounce", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-force");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "stale", "utf8");
    await setMtime(db, 90);
    const lastSweep = path.join(home, ".last-sweep");
    await writeFile(lastSweep, "", "utf8");
    await setMtime(lastSweep, 0);

    const report = await sweep({
      scope: "all",
      home,
      now: new Date(),
      force: true,
    });

    expect(report.reaped.length).toBeGreaterThanOrEqual(1);
  });
});

describe("sweep — dryRun", () => {
  it("reports reapable entries without deleting anything", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-dry");
    const db = path.join(projectDir, "milknado", "milknado.db");
    await writeFile(db, "x", "utf8");
    await setMtime(db, 90);

    const report = await sweep({
      scope: "all",
      home,
      now: new Date(),
      dryRun: true,
    });

    expect(report.reaped.map((r) => r.path)).toContain(db);
    expect((await stat(db)).isFile()).toBe(true);
  });
});

describe("sweep — sidecar edge cases", () => {
  it("treats an empty .path sidecar as a dead target", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-empty-path");
    const wt = path.join(projectDir, "worktrees", "-Users-paul-empty");
    await mkdir(wt, { recursive: true });
    await writeFile(path.join(wt, ".path"), "   \n", "utf8");
    await setMtime(wt, 120);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).toContain(wt);
  });

  it("treats a missing .path sidecar as a dead target", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-no-sidecar");
    const wt = path.join(projectDir, "worktrees", "-Users-paul-nosidecar");
    await mkdir(wt, { recursive: true });
    await setMtime(wt, 120);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.reaped.map((r) => r.path)).toContain(wt);
  });

  it("ignores non-directory entries under worktrees/ and runs/", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-files");
    const wt = path.join(projectDir, "worktrees", "-Users-paul-files");
    await mkdir(path.join(wt, "runs"), { recursive: true });
    await writeFile(path.join(wt, ".path"), `${wt}\n`, "utf8");
    // stray file under worktrees/
    await writeFile(
      path.join(projectDir, "worktrees", "stray.txt"),
      "x",
      "utf8",
    );
    // stray file under runs/
    await writeFile(path.join(wt, "runs", "stray.txt"), "x", "utf8");

    const report = await sweep({ scope: "all", home, now: new Date() });

    const reaped = report.reaped.map((r) => r.path);
    expect(reaped).not.toContain(
      path.join(projectDir, "worktrees", "stray.txt"),
    );
    expect(reaped).not.toContain(path.join(wt, "runs", "stray.txt"));
  });

  it("returns durationMs and an empty error list on a clean sweep", async () => {
    const home = await makeHome();
    await createProject(home, "-Users-paul-clean");

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.errors).toEqual([]);
    expect(typeof report.durationMs).toBe("number");
    expect(report.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("scope=project sweeps only the supplied projectDir", async () => {
    const home = await makeHome();
    const a = await createProject(home, "-Users-paul-scoped-a");
    const b = await createProject(home, "-Users-paul-scoped-b");
    const dbA = path.join(a, "milknado", "milknado.db");
    const dbB = path.join(b, "milknado", "milknado.db");
    await writeFile(dbA, "x", "utf8");
    await writeFile(dbB, "x", "utf8");
    await setMtime(dbA, 90);
    await setMtime(dbB, 90);

    const report = await sweep({
      scope: "project",
      home,
      projectDir: a,
      now: new Date(),
    });

    expect(report.scannedProjects).toBe(1);
    const reaped = report.reaped.map((r) => r.path);
    expect(reaped).toContain(dbA);
    expect(reaped).not.toContain(dbB);
  });

  it("returns scannedProjects=0 when ~/.cheese/projects does not exist", async () => {
    const home = await mkdtemp(path.join(os.tmpdir(), "cheese-sweeper-empty-"));
    tempDirs.push(home);

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.scannedProjects).toBe(0);
    expect(report.reaped).toEqual([]);
  });

  it("handles a project dir that has no worktrees/ directory", async () => {
    const home = await makeHome();
    const projectDir = path.join(home, "projects", "-Users-paul-no-wts");
    await mkdir(path.join(projectDir, "milknado"), { recursive: true });
    await mkdir(path.join(projectDir, "shared"), { recursive: true });
    // intentionally NO worktrees/ directory

    const report = await sweep({ scope: "all", home, now: new Date() });

    expect(report.scannedProjects).toBe(1);
    expect(report.errors).toEqual([]);
  });

  it("skips a reap target whose stat fails (broken symlink as orphan)", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-broken-orphan");
    const fs = await import("node:fs/promises");
    const broken = path.join(
      projectDir,
      "worktrees",
      ".reap-12345-broken-symlink",
    );
    await fs.symlink("/nonexistent/path/that/does/not/exist", broken);

    const report = await sweep({ scope: "all", home, now: new Date() });

    // Either reap (succeeded as symlink unlink) or skipped because stat failed.
    // We assert no errors are surfaced, and the orphan didn't crash the sweep.
    expect(report.errors).toEqual([]);
  });

  it("records a rename failure as a non-fatal error in the report", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-readonly-parent");
    const fs = await import("node:fs/promises");
    const wt = path.join(projectDir, "worktrees", ".reap-99999-orphan");
    await fs.mkdir(wt, { recursive: true });
    const worktreesParent = path.dirname(wt);
    // make worktrees/ read-only AFTER creating the orphan, so readdir succeeds
    // but rename inside it fails with EACCES.
    await fs.chmod(worktreesParent, 0o500);

    try {
      const report = await sweep({ scope: "all", home, now: new Date() });
      expect(report.errors.length).toBeGreaterThanOrEqual(1);
      expect(report.errors[0]?.path).toBe(wt);
    } finally {
      await fs.chmod(worktreesParent, 0o755);
    }
  });
});

describe("sweep — atomicity: orphan .reap-* dirs are cleaned", () => {
  it("removes left-over .reap-* siblings on next run", async () => {
    const home = await makeHome();
    const projectDir = await createProject(home, "-Users-paul-orphan");
    const wtDir = path.join(projectDir, "worktrees", "-Users-paul-orphan");
    await mkdir(wtDir, { recursive: true });
    await writeFile(path.join(wtDir, ".path"), `${wtDir}\n`, "utf8");
    const orphan = path.join(projectDir, "worktrees", ".reap-12345-stale-runs");
    await mkdir(orphan, { recursive: true });

    const report = await sweep({ scope: "all", home, now: new Date() });

    await expect(stat(orphan)).rejects.toThrow();
    expect(report.reaped.map((r) => r.path)).toContain(orphan);
  });
});
