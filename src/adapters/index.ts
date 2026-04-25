import type { HarnessAdapter, HarnessName } from "../domain/harness.js";
import { claudeCodeAdapter } from "./claude-code.js";
import { codexAdapter } from "./codex.js";
import { copilotCliAdapter } from "./copilot-cli.js";
import { cursorAdapter } from "./cursor.js";

export const harnessAdapters: Record<HarnessName, HarnessAdapter> = {
  "claude-code": claudeCodeAdapter,
  codex: codexAdapter,
  cursor: cursorAdapter,
  "copilot-cli": copilotCliAdapter,
};

export const harnessNames = Object.keys(harnessAdapters) as HarnessName[];
