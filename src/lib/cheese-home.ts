import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export interface CheeseHomePaths {
  root: string;
  projectDir: string;
  milknadoDb: string;
  worktreeDir: string;
  manifestsDir: string;
  runsDir: string;
  sharedDir: string;
}

export interface CheeseHomeOptions {
  home?: string;
  canonicalRepo?: string;
}

export interface RetentionConfig {
  defaultDays: number;
  milknadoDays?: number;
  manifestsDays?: number;
  runsDays?: number;
  worktreeDays?: number;
}

const DEFAULT_RETENTION_DAYS = 30;
const RETENTION_NUMERIC_KEYS: ReadonlySet<keyof RetentionConfig> = new Set([
  "defaultDays",
  "milknadoDays",
  "manifestsDays",
  "runsDays",
  "worktreeDays",
]);

export function pathSlug(absPath: string): string {
  return absPath.replaceAll("/", "-");
}

export function discoverCanonicalRepo(cwd: string): string {
  const out = runGitWorktreeList(cwd);
  return realpathSync(parseWorktreeMain(out, cwd));
}

export function parseWorktreeMain(out: string, cwd: string): string {
  const firstLine = out.split("\n", 1)[0] ?? "";
  if (!firstLine.startsWith("worktree ")) {
    throw new Error(
      `discoverCanonicalRepo: ${cwd} is not inside a git worktree (no 'worktree' line)`,
    );
  }
  return firstLine.slice("worktree ".length);
}

function runGitWorktreeList(cwd: string): string {
  try {
    return execFileSync("git", ["worktree", "list", "--porcelain"], {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(
      `discoverCanonicalRepo: ${cwd} is not inside a git repo: ${message}`,
    );
  }
}

export function resolveCheeseHome(
  cwd: string,
  options: CheeseHomeOptions = {},
): CheeseHomePaths {
  const root = options.home ?? path.join(os.homedir(), ".cheese");
  const canonicalRepo = options.canonicalRepo ?? discoverCanonicalRepo(cwd);
  const repoSlug = pathSlug(canonicalRepo);
  const worktreePath = realpathSync(cwd);
  const wtSlug = pathSlug(worktreePath);
  const projectDir = path.join(root, "projects", repoSlug);
  const worktreeDir = path.join(projectDir, "worktrees", wtSlug);
  return {
    root,
    projectDir,
    milknadoDb: path.join(projectDir, "milknado", "milknado.db"),
    worktreeDir,
    manifestsDir: path.join(worktreeDir, "manifests"),
    runsDir: path.join(worktreeDir, "runs"),
    sharedDir: path.join(projectDir, "shared"),
  };
}

export function ensureCheeseHome(
  cwd: string,
  options: CheeseHomeOptions = {},
): CheeseHomePaths {
  const paths = resolveCheeseHome(cwd, options);
  mkdirSync(path.dirname(paths.milknadoDb), { recursive: true });
  mkdirSync(paths.manifestsDir, { recursive: true });
  mkdirSync(paths.runsDir, { recursive: true });
  mkdirSync(paths.sharedDir, { recursive: true });
  writeSidecar(paths.worktreeDir, realpathSync(cwd));
  return paths;
}

function writeSidecar(worktreeDir: string, originalPath: string): void {
  writeFileSync(path.join(worktreeDir, ".path"), `${originalPath}\n`, "utf8");
}

export function readRetentionConfig(projectDir: string): RetentionConfig {
  const tomlPath = path.join(projectDir, "shared", "retention.toml");
  let body: string;
  try {
    body = readFileSync(tomlPath, "utf8");
  } catch {
    return { defaultDays: DEFAULT_RETENTION_DAYS };
  }
  return parseRetentionToml(body);
}

function parseRetentionToml(body: string): RetentionConfig {
  const config: Record<string, number> = {
    defaultDays: DEFAULT_RETENTION_DAYS,
  };
  for (const rawLine of body.split(/\r?\n/)) {
    const line = stripComment(rawLine).trim();
    if (line.length === 0 || line.startsWith("[")) {
      continue;
    }
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    if (!RETENTION_NUMERIC_KEYS.has(key as keyof RetentionConfig)) continue;
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed)) {
      config[key] = parsed;
    }
  }
  return config as unknown as RetentionConfig;
}

function stripComment(line: string): string {
  const hash = line.indexOf("#");
  return hash < 0 ? line : line.slice(0, hash);
}
