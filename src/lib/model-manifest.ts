import { readFile } from "node:fs/promises";
import path from "node:path";
import { parse as parseYaml } from "yaml";
import { z } from "zod";
import type { HarnessName } from "../domain/harness.js";

const harnessPinSchema = z.record(z.string().min(1), z.string().min(1));

const pinsByHarnessSchema = z
  .object({
    "claude-code": harnessPinSchema.optional(),
    codex: harnessPinSchema.optional(),
    cursor: harnessPinSchema.optional(),
    "copilot-cli": harnessPinSchema.optional(),
  })
  .strict();

const overrideEntrySchema = z
  .object({
    "claude-code": z.string().min(1).optional(),
    codex: z.string().min(1).optional(),
    cursor: z.string().min(1).optional(),
    "copilot-cli": z.string().min(1).optional(),
  })
  .strict();

const modelManifestSchema = z
  .object({
    pins: pinsByHarnessSchema.optional(),
    overrides: z
      .record(z.string().regex(/^[a-z][a-z0-9-]*$/), overrideEntrySchema)
      .optional(),
  })
  .strict();

export type ModelManifest = z.infer<typeof modelManifestSchema>;

export const MODEL_MANIFEST_FILE = "models.yaml";

export async function readModelManifest(
  projectRoot: string,
): Promise<ModelManifest | null> {
  const manifestPath = path.join(projectRoot, MODEL_MANIFEST_FILE);
  let raw: string;
  try {
    raw = await readFile(manifestPath, "utf8");
  } catch (error) {
    if (isFileNotFound(error)) return null;
    throw error;
  }
  try {
    const parsed = parseYaml(raw) ?? {};
    return modelManifestSchema.parse(parsed);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown parse/validation error";
    throw new Error(`Invalid models.yaml at ${manifestPath}: ${message}`, {
      cause: error,
    });
  }
}

export function applyModelManifest(input: {
  model: string;
  agentName: string;
  harness: HarnessName;
  manifest: ModelManifest | null;
}): string {
  const { model, agentName, harness, manifest } = input;
  if (manifest === null) return model;
  const override = manifest.overrides?.[agentName]?.[harness];
  if (override !== undefined) return override;
  const pin = manifest.pins?.[harness]?.[model];
  if (pin !== undefined) return pin;
  return model;
}

function isFileNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { code?: unknown }).code === "ENOENT"
  );
}
