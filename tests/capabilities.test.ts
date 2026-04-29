import { describe, expect, it } from "vitest";
import { harnessAdapters } from "../src/adapters/index.js";
import { PORTABLE_EVENTS } from "../src/domain/harness.js";
import {
  eventSupport,
  fieldSupport,
  toolSupport,
} from "../src/lib/capabilities.js";

describe("adapter capabilities declarations", () => {
  it("every adapter has a capabilities object", () => {
    for (const [name, adapter] of Object.entries(harnessAdapters)) {
      expect(typeof adapter.capabilities, `${name} missing capabilities`).toBe(
        "object",
      );
      expect(adapter.capabilities.skillFrontmatterKeys).toBeInstanceOf(Set);
      expect(adapter.capabilities.agentFrontmatterKeys).toBeInstanceOf(Set);
      expect(adapter.capabilities.hookEvents).toBeInstanceOf(Set);
      expect(adapter.capabilities.toolNames).toBeInstanceOf(Set);
    }
  });

  it("claude-code declares the expected claude-only skill keys", () => {
    const cc = harnessAdapters["claude-code"].capabilities;
    expect(cc.skillFrontmatterKeys.has("model")).toBe(true);
    expect(cc.skillFrontmatterKeys.has("context")).toBe(true);
  });

  it("claude-code declares the expected claude-only agent keys", () => {
    const cc = harnessAdapters["claude-code"].capabilities;
    for (const key of [
      "skills",
      "color",
      "effort",
      "disallowedTools",
      "permissionMode",
    ]) {
      expect(
        cc.agentFrontmatterKeys.has(key),
        `missing agent key: ${key}`,
      ).toBe(true);
    }
  });

  it("claude-code declares all 9 hook events", () => {
    const cc = harnessAdapters["claude-code"].capabilities;
    expect(cc.hookEvents.size).toBe(9);
    for (const event of [
      "sessionStart",
      "sessionEnd",
      "preToolUse",
      "postToolUse",
      "stop",
    ]) {
      expect(cc.hookEvents.has(event), `missing event: ${event}`).toBe(true);
    }
  });

  it("claude-code declares all claude-only tools", () => {
    const cc = harnessAdapters["claude-code"].capabilities;
    for (const tool of [
      "Agent",
      "Task",
      "NotebookEdit",
      "WebSearch",
      "WebFetch",
      "TodoWrite",
    ]) {
      expect(cc.toolNames.has(tool), `missing tool: ${tool}`).toBe(true);
    }
  });

  it("codex and copilot-cli declare the 3 portable hook events", () => {
    for (const name of ["codex", "copilot-cli"] as const) {
      const adapter = harnessAdapters[name];
      for (const event of PORTABLE_EVENTS) {
        expect(
          adapter.capabilities.hookEvents.has(event),
          `${name} missing portable event: ${event}`,
        ).toBe(true);
      }
    }
  });

  it("cursor declares zero hook events (no hook system)", () => {
    expect(harnessAdapters.cursor.capabilities.hookEvents.size).toBe(0);
  });

  it("non-claude adapters declare no claude-only skill or agent keys", () => {
    for (const name of ["codex", "cursor", "copilot-cli"] as const) {
      const cap = harnessAdapters[name].capabilities;
      expect(cap.skillFrontmatterKeys.size).toBe(0);
      expect(cap.agentFrontmatterKeys.size).toBe(0);
    }
  });

  it("non-claude adapters declare no tool names", () => {
    for (const name of ["codex", "cursor", "copilot-cli"] as const) {
      expect(harnessAdapters[name].capabilities.toolNames.size).toBe(0);
    }
  });
});

describe("fieldSupport", () => {
  it("model is mapped to only claude-code", () => {
    expect(fieldSupport("skill").get("model")).toEqual(["claude-code"]);
  });

  it("context is mapped to only claude-code", () => {
    expect(fieldSupport("skill").get("context")).toEqual(["claude-code"]);
  });

  it("returns a map for agent kind with all expected keys", () => {
    const support = fieldSupport("agent");
    for (const key of [
      "skills",
      "color",
      "effort",
      "disallowedTools",
      "permissionMode",
    ]) {
      expect(support.has(key), `missing agent key: ${key}`).toBe(true);
    }
  });

  it("portable fields like name/description are absent from the map", () => {
    const support = fieldSupport("skill");
    expect(support.has("name")).toBe(false);
    expect(support.has("description")).toBe(false);
  });
});

describe("eventSupport", () => {
  it("portable events are supported by all hook-using adapters", () => {
    const support = eventSupport();
    const hookAdapters = Object.entries(harnessAdapters)
      .filter(([, a]) => a.capabilities.hookEvents.size > 0)
      .map(([name]) => name)
      .sort();
    for (const event of PORTABLE_EVENTS) {
      const supportedBy = (support.get(event) ?? []).slice().sort();
      expect(supportedBy).toEqual(hookAdapters);
    }
  });

  it("stop is supported only by claude-code", () => {
    expect(eventSupport().get("stop")).toEqual(["claude-code"]);
  });

  it("sessionEnd is supported only by claude-code", () => {
    expect(eventSupport().get("sessionEnd")).toEqual(["claude-code"]);
  });
});

describe("toolSupport", () => {
  it("all tools are supported only by claude-code", () => {
    const support = toolSupport();
    for (const [tool, supportedBy] of support) {
      expect(supportedBy, `${tool} should only be claude-code`).toEqual([
        "claude-code",
      ]);
    }
  });

  it("union of all adapter toolNames covers the full claude-only set", () => {
    const support = toolSupport();
    for (const tool of [
      "Agent",
      "Task",
      "NotebookEdit",
      "WebSearch",
      "WebFetch",
      "TodoWrite",
    ]) {
      expect(support.has(tool), `missing tool: ${tool}`).toBe(true);
    }
  });
});
