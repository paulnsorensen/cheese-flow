import { readFileSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { ensureCheeseHome } from "./cheese-home.js";
import { type SweepReport, sweep } from "./sweeper.js";

const DEFAULT_REGISTRY_URL = "https://registry.npmjs.org/cheese-flow/latest";
const DEBOUNCE_MS = 24 * 60 * 60 * 1000;
const SWEEP_FLOOR_MS = 1000;
const UPDATE_FLOOR_MS = 500;
const FETCH_TIMEOUT_MS = 1000;

export interface UpdateNudge {
  version: string;
  current: string;
  message: string;
}

export interface UpdateCheckResult {
  behind: boolean;
  latestVersion: string | null;
}

export interface CheckForUpdateOptions {
  currentVersion: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
  registryUrl?: string;
}

export async function checkForUpdate(
  opts: CheckForUpdateOptions,
): Promise<UpdateCheckResult | null> {
  const fetchFn = opts.fetch ?? fetch;
  const timeoutMs = opts.timeoutMs ?? FETCH_TIMEOUT_MS;
  const url = opts.registryUrl ?? DEFAULT_REGISTRY_URL;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchFn(url, { signal: controller.signal });
    if (!response.ok) return null;
    const body = (await response.json()) as { version?: unknown };
    const latest =
      typeof body.version === "string" && body.version.length > 0
        ? body.version
        : null;
    if (latest === null) return null;
    return {
      behind: latest !== opts.currentVersion,
      latestVersion: latest,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

interface UpdateCheckRecord {
  checked_at: string;
  latest_version: string | null;
  nudged_for_version: string | null;
}

async function readUpdateCheck(
  home: string,
): Promise<UpdateCheckRecord | null> {
  try {
    const body = await readFile(path.join(home, ".update-check"), "utf8");
    const parsed = JSON.parse(body) as Record<string, unknown>;
    return {
      checked_at:
        typeof parsed.checked_at === "string" ? parsed.checked_at : "",
      latest_version:
        typeof parsed.latest_version === "string"
          ? parsed.latest_version
          : null,
      nudged_for_version:
        typeof parsed.nudged_for_version === "string"
          ? parsed.nudged_for_version
          : null,
    };
  } catch {
    return null;
  }
}

async function writeUpdateCheck(
  home: string,
  record: UpdateCheckRecord,
): Promise<void> {
  await writeFile(
    path.join(home, ".update-check"),
    JSON.stringify(record),
    "utf8",
  );
}

export function shouldCheckUpdate(home: string, now: Date): boolean {
  let body: string;
  try {
    body = readFileSync(path.join(home, ".update-check"), "utf8");
  } catch {
    return true;
  }
  try {
    const parsed = JSON.parse(body) as { checked_at?: unknown };
    if (typeof parsed.checked_at !== "string") return true;
    const last = Date.parse(parsed.checked_at);
    if (!Number.isFinite(last)) return true;
    return now.getTime() - last >= DEBOUNCE_MS;
  } catch {
    return true;
  }
}

export async function recordNudgedVersion(
  home: string,
  version: string,
  now: Date,
): Promise<void> {
  await writeUpdateCheck(home, {
    checked_at: now.toISOString(),
    latest_version: version,
    nudged_for_version: version,
  });
}

async function priorNudgedVersion(home: string): Promise<string | null> {
  const record = await readUpdateCheck(home);
  return record?.nudged_for_version ?? null;
}

async function recordCheck(
  home: string,
  latestVersion: string | null,
  nudgedVersion: string | null,
  now: Date,
): Promise<void> {
  await writeUpdateCheck(home, {
    checked_at: now.toISOString(),
    latest_version: latestVersion,
    nudged_for_version: nudgedVersion,
  });
}

export interface RunSessionStartOptions {
  cwd: string;
  home?: string;
  now?: Date;
  maxTimeMs: number;
  currentVersion: string;
  fetch?: typeof fetch;
  log?: (message: string) => void;
  quiet?: boolean;
}

export interface SessionStartResult {
  ok: true;
  sweptReport?: SweepReport;
  updateNudge?: UpdateNudge;
}

export async function runSessionStart(
  opts: RunSessionStartOptions,
): Promise<SessionStartResult> {
  const now = opts.now ?? new Date();
  const log = opts.log ?? ((msg) => process.stdout.write(`${msg}\n`));
  const deadline = Date.now() + opts.maxTimeMs;
  const remaining = () => deadline - Date.now();

  const paths = ensureCheeseHome(
    opts.cwd,
    opts.home ? { home: opts.home } : {},
  );

  const result: SessionStartResult = { ok: true };

  if (remaining() > SWEEP_FLOOR_MS) {
    const report = await sweep({ scope: "all", home: paths.root, now });
    if (!opts.quiet && report.reaped.length > 0) {
      log(`cheese: swept ${report.reaped.length} stale entries`);
    }
    result.sweptReport = report;
  }

  if (remaining() > UPDATE_FLOOR_MS && shouldCheckUpdate(paths.root, now)) {
    const updateOpts: CheckForUpdateOptions = {
      currentVersion: opts.currentVersion,
      timeoutMs: FETCH_TIMEOUT_MS,
    };
    if (opts.fetch) updateOpts.fetch = opts.fetch;
    const update = await checkForUpdate(updateOpts);
    if (update) {
      const prior = await priorNudgedVersion(paths.root);
      if (
        update.behind &&
        update.latestVersion &&
        update.latestVersion !== prior
      ) {
        const nudge: UpdateNudge = {
          version: update.latestVersion,
          current: opts.currentVersion,
          message: `cheese-flow ${update.latestVersion} is available (current: ${opts.currentVersion})`,
        };
        if (!opts.quiet) log(nudge.message);
        await recordCheck(
          paths.root,
          update.latestVersion,
          update.latestVersion,
          now,
        );
        result.updateNudge = nudge;
      } else {
        await recordCheck(paths.root, update.latestVersion, prior, now);
      }
    }
  }

  return result;
}
