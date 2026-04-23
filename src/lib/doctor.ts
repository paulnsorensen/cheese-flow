import { spawn } from "node:child_process";

export type ToolTier = "required" | "recommended" | "suggested";

export type ToolCheck = {
  name: string;
  tier: ToolTier;
  purpose: string;
  installHint: string;
};

export type ToolResult = ToolCheck & {
  ok: boolean;
  version?: string;
  error?: string;
};

export const toolChecks: ToolCheck[] = [
  {
    name: "tilth",
    tier: "required",
    purpose: "Tree-sitter code intelligence used by exploration skills.",
    installHint:
      "Bundled with cheese-flow. If missing, install globally: npm install -g cheese-flow",
  },
  {
    name: "mergiraf",
    tier: "recommended",
    purpose: "Syntax-aware merge driver for resolving conflicts cleanly.",
    installHint: "brew install mergiraf  (or: cargo install mergiraf)",
  },
  {
    name: "rtk",
    tier: "suggested",
    purpose: "Token-optimized CLI proxy for Claude Code sessions.",
    installHint: "cargo install rtk-cli",
  },
];

export async function runToolCheck(check: ToolCheck): Promise<ToolResult> {
  return new Promise<ToolResult>((resolve) => {
    const child = spawn(check.name, ["--version"], { stdio: "pipe" });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", (error: Error) => {
      resolve({ ...check, ok: false, error: error.message });
    });
    child.on("close", (code: number | null) => {
      if (code === 0) {
        const version = (stdout || stderr).trim().split("\n")[0] ?? "";
        resolve(
          version.length > 0
            ? { ...check, ok: true, version }
            : { ...check, ok: true },
        );
      } else {
        resolve({
          ...check,
          ok: false,
          error: `exited with code ${code ?? "unknown"}`,
        });
      }
    });
  });
}

export async function runAllToolChecks(): Promise<ToolResult[]> {
  return Promise.all(toolChecks.map(runToolCheck));
}

const tierLabels: Record<ToolTier, string> = {
  required: "REQUIRED",
  recommended: "RECOMMENDED",
  suggested: "SUGGESTED",
};

export function formatReport(results: ToolResult[]): string {
  const lines: string[] = ["cheese doctor — tool dependency check", ""];

  for (const result of results) {
    const status = result.ok ? "ok" : "missing";
    const tag = tierLabels[result.tier];
    lines.push(`[${tag}] ${result.name}: ${status}`);
    lines.push(`  ${result.purpose}`);
    if (result.ok && result.version) {
      lines.push(`  found: ${result.version}`);
    } else {
      lines.push(`  install: ${result.installHint}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

export function hasBlockingFailure(results: ToolResult[]): boolean {
  return results.some((result) => result.tier === "required" && !result.ok);
}
