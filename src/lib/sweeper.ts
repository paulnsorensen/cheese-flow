import {
  readdir,
  readFile,
  rename,
  rm,
  stat,
  utimes,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { type RetentionConfig, readRetentionConfig } from "./cheese-home.js";

export interface ReapEntry {
  path: string;
  reason: string;
  bytes: number;
}

export interface SweepReport {
  scannedProjects: number;
  reaped: ReapEntry[];
  errors: { path: string; error: string }[];
  durationMs: number;
}

export interface SweepOptions {
  scope: "all" | "project";
  home: string;
  projectDir?: string;
  now?: Date;
  dryRun?: boolean;
  force?: boolean;
}

const DEBOUNCE_MS = 24 * 60 * 60 * 1000;
const ORPHAN_PREFIX = ".reap-";

export async function sweep(opts: SweepOptions): Promise<SweepReport> {
  const start = Date.now();
  const now = opts.now ?? new Date();
  const lastSweep = path.join(opts.home, ".last-sweep");

  if (!opts.force && (await isDebounced(lastSweep, now))) {
    return {
      scannedProjects: 0,
      reaped: [],
      errors: [],
      durationMs: Date.now() - start,
    };
  }

  const projectDirs = await collectProjectDirs(opts);
  const reaped: ReapEntry[] = [];
  const errors: { path: string; error: string }[] = [];
  for (const projectDir of projectDirs) {
    const config = readRetentionConfig(projectDir);
    await sweepProject(
      projectDir,
      config,
      now,
      opts.dryRun ?? false,
      reaped,
      errors,
    );
  }
  if (!opts.dryRun) {
    await touchFile(lastSweep, now);
  }
  return {
    scannedProjects: projectDirs.length,
    reaped,
    errors,
    durationMs: Date.now() - start,
  };
}

async function isDebounced(lastSweep: string, now: Date): Promise<boolean> {
  try {
    const info = await stat(lastSweep);
    return now.getTime() - info.mtimeMs < DEBOUNCE_MS;
  } catch {
    return false;
  }
}

async function collectProjectDirs(opts: SweepOptions): Promise<string[]> {
  if (opts.scope === "project" && opts.projectDir) {
    return [opts.projectDir];
  }
  const projectsRoot = path.join(opts.home, "projects");
  let entries: { name: string; isDirectory(): boolean }[];
  try {
    entries = await readdir(projectsRoot, { withFileTypes: true });
  } catch {
    return [];
  }
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(projectsRoot, entry.name));
}

async function sweepProject(
  projectDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  await reapMilknado(projectDir, config, now, dryRun, reaped, errors);
  await reapWorktrees(projectDir, config, now, dryRun, reaped, errors);
}

async function reapMilknado(
  projectDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  const db = path.join(projectDir, "milknado", "milknado.db");
  const days = config.milknadoDays ?? config.defaultDays;
  if (await isOlderThan(db, now, days)) {
    await reap(db, `milknado.db older than ${days}d`, dryRun, reaped, errors);
  }
}

async function reapWorktrees(
  projectDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  const wtRoot = path.join(projectDir, "worktrees");
  let entries: { name: string; isDirectory(): boolean }[];
  try {
    entries = await readdir(wtRoot, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const child = path.join(wtRoot, entry.name);
    if (entry.name.startsWith(ORPHAN_PREFIX)) {
      await reap(child, "orphaned reap-tmp", dryRun, reaped, errors);
      continue;
    }
    if (!entry.isDirectory()) continue;
    await sweepWorktree(child, config, now, dryRun, reaped, errors);
  }
}

async function sweepWorktree(
  worktreeDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  const wtDays = config.worktreeDays ?? config.defaultDays;
  if (
    (await isOlderThan(worktreeDir, now, wtDays)) &&
    !(await sidecarTargetExists(worktreeDir))
  ) {
    await reap(
      worktreeDir,
      `worktree dir older than ${wtDays}d AND .path target gone`,
      dryRun,
      reaped,
      errors,
    );
    return;
  }
  await reapManifests(worktreeDir, config, now, dryRun, reaped, errors);
  await reapRuns(worktreeDir, config, now, dryRun, reaped, errors);
}

async function reapManifests(
  worktreeDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  const manifests = path.join(worktreeDir, "manifests");
  const days = config.manifestsDays ?? config.defaultDays;
  if (await isOlderThan(manifests, now, days)) {
    await reap(
      manifests,
      `manifests older than ${days}d`,
      dryRun,
      reaped,
      errors,
    );
  }
}

async function reapRuns(
  worktreeDir: string,
  config: RetentionConfig,
  now: Date,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  const runs = path.join(worktreeDir, "runs");
  const days = config.runsDays ?? config.defaultDays;
  let entries: { name: string; isDirectory(): boolean }[];
  try {
    entries = await readdir(runs, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const runDir = path.join(runs, entry.name);
    if (await isOlderThan(runDir, now, days)) {
      await reap(runDir, `run dir older than ${days}d`, dryRun, reaped, errors);
    }
  }
}

async function sidecarTargetExists(worktreeDir: string): Promise<boolean> {
  let body: string;
  try {
    body = await readFile(path.join(worktreeDir, ".path"), "utf8");
  } catch {
    return false;
  }
  const target = body.trim();
  if (target.length === 0) return false;
  try {
    await stat(target);
    return true;
  } catch {
    return false;
  }
}

async function isOlderThan(
  target: string,
  now: Date,
  days: number,
): Promise<boolean> {
  try {
    const info = await stat(target);
    const ageMs = now.getTime() - info.mtimeMs;
    return ageMs > days * 24 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}

async function reap(
  target: string,
  reason: string,
  dryRun: boolean,
  reaped: ReapEntry[],
  errors: { path: string; error: string }[],
): Promise<void> {
  let bytes = 0;
  try {
    const info = await stat(target);
    bytes = info.isDirectory() ? 0 : info.size;
  } catch {
    return;
  }
  reaped.push({ path: target, reason, bytes });
  if (dryRun) return;
  try {
    const tmp = `${path.dirname(target)}/${ORPHAN_PREFIX}${Date.now()}-${path.basename(target)}`;
    await rename(target, tmp);
    await rm(tmp, { recursive: true, force: true });
  } catch (error) {
    errors.push({
      path: target,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function touchFile(target: string, now: Date): Promise<void> {
  try {
    await writeFile(target, "", { flag: "a" });
    await utimes(target, now, now);
  } catch {
    /* best effort */
  }
}
