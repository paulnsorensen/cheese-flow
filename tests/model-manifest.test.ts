import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  applyModelManifest,
  type ModelManifest,
  readModelManifest,
} from "../src/lib/model-manifest.js";

const created: string[] = [];

afterEach(async () => {
  await Promise.all(
    created.splice(0).map((dir) => rm(dir, { recursive: true, force: true })),
  );
});

async function makeProjectRoot(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cheese-flow-manifest-"));
  created.push(dir);
  return dir;
}

describe("readModelManifest", () => {
  it("returns null when models.yaml is absent", async () => {
    const root = await makeProjectRoot();
    expect(await readModelManifest(root)).toBeNull();
  });

  it("parses pins and overrides", async () => {
    const root = await makeProjectRoot();
    await writeFile(
      path.join(root, "models.yaml"),
      [
        "pins:",
        "  claude-code:",
        "    sonnet: claude-sonnet-4-6",
        "    opus: claude-opus-4-7",
        "  codex:",
        "    gpt-5-codex: gpt-5.3-codex",
        "overrides:",
        "  age-correctness:",
        "    claude-code: claude-opus-4-7",
        "",
      ].join("\n"),
      "utf8",
    );
    const manifest = await readModelManifest(root);
    expect(manifest).toEqual({
      pins: {
        "claude-code": {
          sonnet: "claude-sonnet-4-6",
          opus: "claude-opus-4-7",
        },
        codex: { "gpt-5-codex": "gpt-5.3-codex" },
      },
      overrides: {
        "age-correctness": { "claude-code": "claude-opus-4-7" },
      },
    });
  });

  it("rejects unknown harness keys via strict schema", async () => {
    const root = await makeProjectRoot();
    await writeFile(
      path.join(root, "models.yaml"),
      "pins:\n  qwen-code:\n    sonnet: foo\n",
      "utf8",
    );
    await expect(readModelManifest(root)).rejects.toThrow();
  });

  it("treats an empty file as an empty manifest", async () => {
    const root = await makeProjectRoot();
    await writeFile(path.join(root, "models.yaml"), "", "utf8");
    expect(await readModelManifest(root)).toEqual({});
  });

  it("propagates non-ENOENT read errors", async () => {
    const root = await makeProjectRoot();
    await mkdir(path.join(root, "models.yaml"), { recursive: true });
    await expect(readModelManifest(root)).rejects.toThrow();
  });
});

describe("applyModelManifest", () => {
  const baseInput = {
    model: "sonnet",
    agentName: "age-correctness",
    harness: "claude-code" as const,
  };

  it("returns the input model when manifest is null", () => {
    expect(applyModelManifest({ ...baseInput, manifest: null })).toBe("sonnet");
  });

  it("returns the input model when no pin or override matches", () => {
    const manifest: ModelManifest = {
      pins: { codex: { "gpt-5-codex": "gpt-5.3-codex" } },
    };
    expect(applyModelManifest({ ...baseInput, manifest })).toBe("sonnet");
  });

  it("substitutes a pinned version when the alias matches the harness pin", () => {
    const manifest: ModelManifest = {
      pins: { "claude-code": { sonnet: "claude-sonnet-4-6" } },
    };
    expect(applyModelManifest({ ...baseInput, manifest })).toBe(
      "claude-sonnet-4-6",
    );
  });

  it("uses an override that supersedes any matching pin", () => {
    const manifest: ModelManifest = {
      pins: { "claude-code": { sonnet: "claude-sonnet-4-6" } },
      overrides: {
        "age-correctness": { "claude-code": "claude-opus-4-7" },
      },
    };
    expect(applyModelManifest({ ...baseInput, manifest })).toBe(
      "claude-opus-4-7",
    );
  });

  it("ignores overrides for a different agent", () => {
    const manifest: ModelManifest = {
      overrides: { "age-security": { "claude-code": "claude-opus-4-7" } },
    };
    expect(applyModelManifest({ ...baseInput, manifest })).toBe("sonnet");
  });

  it("ignores pins for a different harness", () => {
    const manifest: ModelManifest = {
      pins: { codex: { sonnet: "gpt-5.5" } },
    };
    expect(applyModelManifest({ ...baseInput, manifest })).toBe("sonnet");
  });
});
