import { harnessAdapters } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";

export function fieldSupport(
  kind: "skill" | "agent",
): Map<string, HarnessName[]> {
  const result = new Map<string, HarnessName[]>();
  for (const [name, adapter] of Object.entries(harnessAdapters) as Array<
    [HarnessName, (typeof harnessAdapters)[HarnessName]]
  >) {
    const keys =
      kind === "skill"
        ? adapter.capabilities.skillFrontmatterKeys
        : adapter.capabilities.agentFrontmatterKeys;
    for (const key of keys) {
      const existing = result.get(key) ?? [];
      existing.push(name);
      result.set(key, existing);
    }
  }
  return result;
}

export function eventSupport(): Map<string, HarnessName[]> {
  const result = new Map<string, HarnessName[]>();
  for (const [name, adapter] of Object.entries(harnessAdapters) as Array<
    [HarnessName, (typeof harnessAdapters)[HarnessName]]
  >) {
    for (const event of adapter.capabilities.hookEvents) {
      const existing = result.get(event) ?? [];
      existing.push(name);
      result.set(event, existing);
    }
  }
  return result;
}

export function toolSupport(): Map<string, HarnessName[]> {
  const result = new Map<string, HarnessName[]>();
  for (const [name, adapter] of Object.entries(harnessAdapters) as Array<
    [HarnessName, (typeof harnessAdapters)[HarnessName]]
  >) {
    for (const tool of adapter.capabilities.toolNames) {
      const existing = result.get(tool) ?? [];
      existing.push(name);
      result.set(tool, existing);
    }
  }
  return result;
}
