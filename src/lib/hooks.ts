import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { HarnessName } from "./harnesses.js";

const hookEntrySchema = z.object({
  type: z.string().min(1),
  command: z.string().min(1),
  timeout: z.number().int().positive().optional(),
});

export const hooksSourceSchema = z.record(z.string(), z.array(hookEntrySchema));

const PORTABLE_EVENTS = ["sessionStart", "preToolUse", "postToolUse"] as const;
type PortableEvent = (typeof PORTABLE_EVENTS)[number];

export type HookEntry = {
  type: string;
  command: string;
  timeout?: number;
};

export type HooksSource = Partial<Record<string, HookEntry[]>>;

const PASCAL_MAP: Record<PortableEvent, string> = {
  sessionStart: "SessionStart",
  preToolUse: "PreToolUse",
  postToolUse: "PostToolUse",
};

const DEFAULT_TIMEOUT = 600;

function filterPortableEvents(source: HooksSource): {
  portable: Partial<Record<string, HookEntry[]>>;
  dropped: string[];
} {
  const portable: Partial<Record<string, HookEntry[]>> = {};
  const dropped: string[] = [];
  const portableSet: ReadonlySet<string> = new Set(PORTABLE_EVENTS);

  for (const [event, entries] of Object.entries(source)) {
    if (portableSet.has(event)) {
      portable[event] = entries;
    } else {
      console.warn(`[cheese-flow] skipping non-portable hook event: ${event}`);
      dropped.push(event);
    }
  }

  return { portable, dropped };
}

function buildClaudeCodeHooks(
  portable: Partial<Record<string, HookEntry[]>>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries !== undefined) {
      result[event] = entries;
    }
  }
  return result;
}

function buildCodexHooks(
  portable: Partial<Record<string, HookEntry[]>>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries !== undefined) {
      const pascalKey = PASCAL_MAP[event];
      result[pascalKey] = entries.map((entry) => ({
        matcher: "*",
        hooks: [
          {
            type: entry.type,
            command: entry.command,
            timeout: entry.timeout ?? DEFAULT_TIMEOUT,
          },
        ],
      }));
    }
  }
  return result;
}

async function writeHooksJson(
  outputRoot: string,
  payload: Record<string, unknown>,
): Promise<string> {
  await mkdir(outputRoot, { recursive: true });
  const outputPath = path.join(outputRoot, "hooks.json");
  await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return outputPath;
}

export async function emitHooks(
  harness: HarnessName,
  source: HooksSource,
  outputRoot: string,
): Promise<false | string> {
  if (harness === "cursor") {
    console.info(
      "[cheese-flow] hooks not supported in Cursor target; skipping",
    );
    return false;
  }

  const { portable } = filterPortableEvents(source);

  if (harness === "claude-code") {
    const hooks = buildClaudeCodeHooks(portable);
    return writeHooksJson(outputRoot, { hooks });
  }

  if (harness === "copilot-cli") {
    const hooks = buildClaudeCodeHooks(portable);
    return writeHooksJson(outputRoot, { version: 1, hooks });
  }

  // codex
  const hooks = buildCodexHooks(portable);
  return writeHooksJson(outputRoot, { hooks });
}
