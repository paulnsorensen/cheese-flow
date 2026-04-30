import type { Dirent } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { harnessAdapters } from "../src/adapters/index.js";
import { CHEESE_DIR } from "../src/domain/harness.js";
import { checkBodyHarnessIdioms } from "../src/lib/harness-compat.js";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

async function readMarkdownFiles(dir: string): Promise<string[]> {
  const collected: string[] = [];
  let entries: Dirent[];
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return collected;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collected.push(...(await readMarkdownFiles(full)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      collected.push(full);
    }
  }
  return collected;
}

describe("AC1: CHEESE_DIR constant", () => {
  it('exports CHEESE_DIR === ".cheese" from src/domain/harness.ts', () => {
    expect(CHEESE_DIR).toBe(".cheese");
  });
});

describe("AC2: bootstrapHook capability flag", () => {
  it("declares bootstrapHook as a boolean on every adapter's capabilities", () => {
    for (const [name, adapter] of Object.entries(harnessAdapters)) {
      const caps = adapter.capabilities as { bootstrapHook?: unknown };
      expect(
        typeof caps.bootstrapHook,
        `adapter ${name} must expose capabilities.bootstrapHook as boolean`,
      ).toBe("boolean");
    }
  });

  it("enables bootstrapHook for claude-code, codex, and copilot-cli", () => {
    const caps = (name: string) =>
      (
        harnessAdapters[name as keyof typeof harnessAdapters].capabilities as {
          bootstrapHook?: boolean;
        }
      ).bootstrapHook;
    expect(caps("claude-code")).toBe(true);
    expect(caps("codex")).toBe(true);
    expect(caps("copilot-cli")).toBe(true);
  });

  it("disables bootstrapHook for cursor", () => {
    const cursorCaps = harnessAdapters.cursor.capabilities as {
      bootstrapHook?: boolean;
    };
    expect(cursorCaps.bootstrapHook).toBe(false);
  });
});

describe("AC3: <harness>/ placeholder removal", () => {
  it("contains no '<harness>/' substring in commands/ or skills/ markdown", async () => {
    const commandsDir = path.join(REPO_ROOT, "commands");
    const skillsDir = path.join(REPO_ROOT, "skills");
    const files = [
      ...(await readMarkdownFiles(commandsDir)),
      ...(await readMarkdownFiles(skillsDir)),
    ];
    expect(files.length).toBeGreaterThan(0);
    const offenders: string[] = [];
    for (const file of files) {
      const body = await readFile(file, "utf8");
      if (body.includes("<harness>/")) {
        offenders.push(path.relative(REPO_ROOT, file));
      }
    }
    expect(
      offenders,
      `files still containing "<harness>/": ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});

describe("AC4: body-harness-placeholder lint rule", () => {
  it("flags '<harness>/specs/foo.md' with rule body-harness-placeholder", () => {
    const findings = checkBodyHarnessIdioms(
      "This writes to `<harness>/specs/foo.md`",
    );
    const placeholderFindings = findings.filter(
      (f) => f.rule === "body-harness-placeholder",
    );
    expect(placeholderFindings.length).toBeGreaterThanOrEqual(1);
    expect(placeholderFindings[0]?.severity).toBe("error");
  });

  it("does not flag '.cheese/specs/foo.md' with body-harness-placeholder", () => {
    const findings = checkBodyHarnessIdioms(
      "This writes to `.cheese/specs/foo.md`",
    );
    const placeholderFindings = findings.filter(
      (f) => f.rule === "body-harness-placeholder",
    );
    expect(placeholderFindings).toEqual([]);
  });

  it("includes '.cheese/' as the recommended replacement in the message", () => {
    const findings = checkBodyHarnessIdioms(
      "This writes to `<harness>/research/foo.md`",
    );
    const placeholderFindings = findings.filter(
      (f) => f.rule === "body-harness-placeholder",
    );
    expect(placeholderFindings.length).toBeGreaterThanOrEqual(1);
    const finding = placeholderFindings[0];
    expect(finding?.message).toContain(".cheese/");
  });
});

describe("AC6: .gitignore contains .cheese/", () => {
  it("repo-root .gitignore contains a line matching exactly '.cheese/'", async () => {
    const gitignorePath = path.join(REPO_ROOT, ".gitignore");
    const body = await readFile(gitignorePath, "utf8");
    const lines = body.split(/\r?\n/);
    expect(lines).toContain(".cheese/");
  });
});

describe("AC5: project-root hooks.json registers cheese-bootstrap.sh", () => {
  it("hooks.json exists at the repo root", async () => {
    const hooksPath = path.join(REPO_ROOT, "hooks.json");
    const stats = await stat(hooksPath);
    expect(stats.isFile()).toBe(true);
  });

  it("hooks.json parses as JSON and registers cheese-bootstrap.sh on sessionStart", async () => {
    const hooksPath = path.join(REPO_ROOT, "hooks.json");
    const body = await readFile(hooksPath, "utf8");
    const parsed = JSON.parse(body) as Record<string, unknown>;
    // The portable hook source uses camelCase event keys (top-level or under .hooks).
    const hooksRoot =
      (parsed.hooks as Record<string, unknown> | undefined) ?? parsed;
    const sessionStart = (hooksRoot as Record<string, unknown>)
      .sessionStart as unknown;
    expect(Array.isArray(sessionStart)).toBe(true);
    const entries = sessionStart as Array<Record<string, unknown>>;
    expect(entries.length).toBeGreaterThanOrEqual(1);
    const referencesScript = entries.some((entry) => {
      const command =
        typeof entry.command === "string" ? entry.command : undefined;
      return command !== undefined && command.includes("cheese-bootstrap.sh");
    });
    expect(
      referencesScript,
      "expected at least one sessionStart entry to reference cheese-bootstrap.sh",
    ).toBe(true);
  });
});
