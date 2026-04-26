import { z } from "zod";
import type { HarnessName } from "../domain/harness.js";

const slug = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/u, "Must be lowercase kebab-case.");

const skillFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  license: z.string().min(1).optional(),
  compatibility: z.string().min(1).max(500).optional(),
  "allowed-tools": z
    .union([z.array(z.string().min(1)), z.string().min(1)])
    .optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

const commandFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  "argument-hint": z.string().min(1).max(200).optional(),
});

const harnessModelSchema = z.object({
  default: z.string().min(1),
  "claude-code": z.string().min(1).optional(),
  codex: z.string().min(1).optional(),
  cursor: z.string().min(1).optional(),
  "copilot-cli": z.string().min(1).optional(),
});

const agentFrontmatterSchema = z.object({
  name: slug,
  description: z.string().min(1).max(1024),
  models: harnessModelSchema,
  tools: z.array(z.string().min(1)).default([]),
});

export type SkillFrontmatter = z.infer<typeof skillFrontmatterSchema>;
export type CommandFrontmatter = z.infer<typeof commandFrontmatterSchema>;
export type AgentFrontmatter = z.infer<typeof agentFrontmatterSchema>;

export function parseSkillFrontmatter(data: unknown): SkillFrontmatter {
  return skillFrontmatterSchema.parse(data);
}

export function parseCommandFrontmatter(data: unknown): CommandFrontmatter {
  return commandFrontmatterSchema.parse(data);
}

export function parseAgentFrontmatter(data: unknown): AgentFrontmatter {
  return agentFrontmatterSchema.parse(data);
}

export function resolveModel(
  models: AgentFrontmatter["models"],
  harness: HarnessName,
): string {
  return models[harness] ?? models.default;
}
