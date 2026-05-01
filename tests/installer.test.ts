import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  access,
  chmod,
  cp,
  mkdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";

const createdDirectories: string[] = [];
const execFileAsync = promisify(execFile);
const tsxCliPath = path.resolve("node_modules", "tsx", "dist", "cli.mjs");

afterEach(async () => {
  await Promise.all(
    createdDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

async function makeDirectory(prefix: string): Promise<string> {
  const directory = path.resolve(".test-runtime", `${prefix}-${randomUUID()}`);
  await mkdir(directory, { recursive: true });
  createdDirectories.push(directory);
  return directory;
}

async function makeProjectRoot(prefix: string): Promise<string> {
  const projectRoot = await makeDirectory(prefix);
  await cp(path.resolve("agents"), path.join(projectRoot, "agents"), {
    recursive: true,
  });
  await cp(path.resolve("skills"), path.join(projectRoot, "skills"), {
    recursive: true,
  });
  await cp(path.resolve("commands"), path.join(projectRoot, "commands"), {
    recursive: true,
  });
  return projectRoot;
}

async function writeExecutable(
  directory: string,
  name: string,
  content = "#!/bin/sh\nexit 0\n",
): Promise<void> {
  const filePath = path.join(directory, name);
  await writeFile(filePath, content, "utf8");
  await chmod(filePath, 0o755);
}

async function runCheeseInstall(
  args: string[],
  env: NodeJS.ProcessEnv,
): Promise<{ stdout: string; stderr: string }> {
  return execFileAsync(
    process.execPath,
    [tsxCliPath, "src/index.ts", "install", ...args],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        ...env,
      },
    },
  );
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function combinedOutput(error: { stdout?: string; stderr?: string }): string {
  return `${error.stdout ?? ""}${error.stderr ?? ""}`;
}

describe("cheese install", () => {
  it("fails with guidance and emits no bundles when auto-detect finds nothing", async () => {
    const projectRoot = await makeProjectRoot("install-no-detect");
    const emptyPath = await makeDirectory("empty-bin");

    const error = await runCheeseInstall(["--project-root", projectRoot], {
      PATH: emptyPath,
    }).then(
      () => undefined,
      (caughtError) =>
        caughtError as { code?: number; stdout?: string; stderr?: string },
    );

    expect(error?.code).toBe(1);
    expect(combinedOutput(error ?? {})).toContain(
      "No installed harnesses detected",
    );
    expect(combinedOutput(error ?? {})).toContain("cheese compile");
    await expect(pathExists(path.join(projectRoot, ".claude"))).resolves.toBe(
      false,
    );
    await expect(pathExists(path.join(projectRoot, ".codex"))).resolves.toBe(
      false,
    );
    await expect(pathExists(path.join(projectRoot, ".copilot"))).resolves.toBe(
      false,
    );
    await expect(pathExists(path.join(projectRoot, ".cursor"))).resolves.toBe(
      false,
    );
  });

  it("auto-detects cursor and copilot, compiles only those bundles, and installs copilot", async () => {
    const projectRoot = await makeProjectRoot("install-auto");
    const binDirectory = await makeDirectory("install-auto-bin");
    const copilotLog = path.join(projectRoot, "copilot.log");

    await mkdir(path.join(projectRoot, ".cursor"), { recursive: true });
    await writeExecutable(
      binDirectory,
      "copilot",
      `#!/bin/sh\nprintf '%s\\n' "$*" >> "${copilotLog}"\nexit 0\n`,
    );

    const result = await runCheeseInstall(["--project-root", projectRoot], {
      PATH: binDirectory,
    });

    expect(result.stdout).toContain("[installed] Cursor");
    expect(result.stdout).toContain("[installed] GitHub Copilot CLI");
    expect(result.stdout).toContain("[skipped] Claude Code");
    expect(result.stdout).toContain("[skipped] Codex");
    await expect(pathExists(path.join(projectRoot, ".cursor"))).resolves.toBe(
      true,
    );
    await expect(pathExists(path.join(projectRoot, ".copilot"))).resolves.toBe(
      true,
    );
    await expect(pathExists(path.join(projectRoot, ".claude"))).resolves.toBe(
      false,
    );
    await expect(pathExists(path.join(projectRoot, ".codex"))).resolves.toBe(
      false,
    );
    await expect(readFile(copilotLog, "utf8")).resolves.toContain(
      `plugin install ${path.join(projectRoot, ".copilot")}`,
    );
  });

  it("marks Claude Code and Codex as manual and emits local marketplace helpers", async () => {
    const projectRoot = await makeProjectRoot("install-manual");
    const binDirectory = await makeDirectory("install-manual-bin");

    await writeExecutable(binDirectory, "claude");
    await writeExecutable(binDirectory, "codex");

    const error = await runCheeseInstall(
      ["--project-root", projectRoot, "--harness", "claude-code,codex"],
      {
        PATH: binDirectory,
      },
    ).then(
      () => undefined,
      (caughtError) =>
        caughtError as { code?: number; stdout?: string; stderr?: string },
    );

    const output = combinedOutput(error ?? {});
    expect(error?.code).toBe(1);
    expect(output).toContain("[manual] Claude Code");
    expect(output).toContain(
      `claude plugin marketplace add ${JSON.stringify(
        path.join(projectRoot, ".claude"),
      )}`,
    );
    expect(output).toContain("[manual] Codex");
    expect(output).toContain(
      `codex plugin marketplace add ${JSON.stringify(
        path.join(projectRoot, ".codex"),
      )}`,
    );
    expect(output).toContain("Restart Codex.");
    expect(output).toContain('Open /plugins, choose "cheese-flow-local"');

    const claudeMarketplace = JSON.parse(
      await readFile(
        path.join(projectRoot, ".claude", ".claude-plugin", "marketplace.json"),
        "utf8",
      ),
    ) as { plugins: Array<{ source: string }> };
    expect(claudeMarketplace.plugins[0]?.source).toBe("./");

    const codexMarketplace = JSON.parse(
      await readFile(
        path.join(
          projectRoot,
          ".codex",
          ".agents",
          "plugins",
          "marketplace.json",
        ),
        "utf8",
      ),
    ) as {
      plugins: Array<{
        source: { source: string; path: string };
      }>;
    };
    expect(codexMarketplace.plugins[0]?.source).toEqual({
      source: "local",
      path: "./",
    });
  });

  it("fails a selected copilot install when the copilot CLI is unavailable", async () => {
    const projectRoot = await makeProjectRoot("install-copilot-missing");
    const emptyPath = await makeDirectory("install-copilot-missing-bin");

    const error = await runCheeseInstall(
      ["--project-root", projectRoot, "--harness", "copilot-cli"],
      {
        PATH: emptyPath,
      },
    ).then(
      () => undefined,
      (caughtError) =>
        caughtError as { code?: number; stdout?: string; stderr?: string },
    );

    expect(error?.code).toBe(1);
    expect(combinedOutput(error ?? {})).toContain(
      "[failed] GitHub Copilot CLI",
    );
    expect(combinedOutput(error ?? {})).toContain(
      'requires the "copilot" command on PATH',
    );
    await expect(pathExists(path.join(projectRoot, ".copilot"))).resolves.toBe(
      true,
    );
  });
});
