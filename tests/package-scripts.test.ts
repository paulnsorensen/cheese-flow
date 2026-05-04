import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

type PackageJson = {
  scripts?: Record<string, string>;
};

describe("package scripts", () => {
  it("expose auto-detect and explicit all-harness install entrypoints", async () => {
    const packageJson = JSON.parse(
      await readFile(path.resolve("package.json"), "utf8"),
    ) as PackageJson;

    expect(packageJson.scripts).toMatchObject({
      "compile:all": "tsx src/index.ts compile",
      "install:all":
        "tsx src/index.ts install --harness claude-code,codex,cursor,copilot-cli",
      "install:auto": "tsx src/index.ts install",
    });
  });
});
