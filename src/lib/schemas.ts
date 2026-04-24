import { z } from "zod";
import type { HarnessName } from "./harnesses.js";

const slug = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/u, "Must be lowercase kebab-case.");

export const skillFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  license: z.string().min(1).optional(),
  compatibility: z.string().min(1).max(500).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  "allowed-tools": z
    .union([z.array(z.string().min(1)), z.string().min(1)])
    .optional(),
});

export const commandFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  "argument-hint": z.string().min(1).max(200).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

const harnessModelSchema = z.object({
  default: z.string().min(1),
  "claude-code": z.string().min(1).optional(),
  codex: z.string().min(1).optional(),
});

export const agentFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  models: harnessModelSchema,
  tools: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export type SkillFrontmatter = z.infer<typeof skillFrontmatterSchema>;
export type AgentFrontmatter = z.infer<typeof agentFrontmatterSchema>;

export function resolveModel(
  models: AgentFrontmatter["models"],
  harness: HarnessName,
): string {
  return models[harness] ?? models.default;
}
