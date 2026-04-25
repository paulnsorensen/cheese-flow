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
type PortableHooks = Partial<Record<PortableEvent, HookEntry[]>>;

const PASCAL_MAP: Record<PortableEvent, string> = {
  sessionStart: "SessionStart",
  preToolUse: "PreToolUse",
  postToolUse: "PostToolUse",
};

const DEFAULT_TIMEOUT = 600;

type HookAdapter = {
  build(portable: PortableHooks): Record<string, unknown> | null;
};

function camelCaseHooks(portable: PortableHooks): Record<string, HookEntry[]> {
  const result: Record<string, HookEntry[]> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries !== undefined) result[event] = entries;
  }
  return result;
}

function pascalMatcherHooks(
  portable: PortableHooks,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const event of PORTABLE_EVENTS) {
    const entries = portable[event];
    if (entries === undefined) continue;
    result[PASCAL_MAP[event]] = entries.map((entry) => ({
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
  return result;
}

const hookAdapters: Record<HarnessName, HookAdapter> = {
  "claude-code": {
    build: (portable) => ({ hooks: camelCaseHooks(portable) }),
  },
  "copilot-cli": {
    build: (portable) => ({ version: 1, hooks: camelCaseHooks(portable) }),
  },
  codex: {
    build: (portable) => ({ hooks: pascalMatcherHooks(portable) }),
  },
  cursor: {
    build: () => null,
  },
};

function filterPortableEvents(source: HooksSource): PortableHooks {
  const portable: PortableHooks = {};
  const portableSet: ReadonlySet<string> = new Set(PORTABLE_EVENTS);

  for (const [event, entries] of Object.entries(source)) {
    if (entries === undefined) continue;
    if (portableSet.has(event)) {
      portable[event as PortableEvent] = entries;
    } else {
      console.warn(`[cheese-flow] skipping non-portable hook event: ${event}`);
    }
  }

  return portable;
}

export async function emitHooks(
  harness: HarnessName,
  source: HooksSource,
  outputRoot: string,
): Promise<false | string> {
  const adapter = hookAdapters[harness];
  const portable = filterPortableEvents(source);
  const payload = adapter.build(portable);

  if (payload === null) {
    console.info(
      `[cheese-flow] hooks not supported in ${harness} target; skipping`,
    );
    return false;
  }

  await mkdir(outputRoot, { recursive: true });
  const outputPath = path.join(outputRoot, "hooks.json");
  await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return outputPath;
}
