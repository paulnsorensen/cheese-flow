import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseFrontmatter } from "../src/lib/frontmatter.js";
import {
  parseCommandFrontmatter,
  parseSkillFrontmatter,
} from "../src/lib/schemas.js";

const root = path.resolve(".");

async function readSource(relativePath: string): Promise<string> {
  return readFile(path.join(root, relativePath), "utf8");
}

describe("/cure flow artifacts", () => {
  // commands/cure.md — D1 (name=cure), §Approach (loop phases),
  // §Slice (points at skills/cure/SKILL.md).
  it("ships a thin /cure command shim that points at the skill", async () => {
    const source = await readSource("commands/cure.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);

    expect(command.name).toBe("cure");
    expect(command.description).toMatch(/cure|apply/iu);
    // Body lists the loop phases and routes to the skill.
    expect(parsed.body).toMatch(/load/iu);
    expect(parsed.body).toMatch(/user\s*gate|gate/iu);
    expect(parsed.body).toMatch(/apply/iu);
    expect(parsed.body).toMatch(/re-?age/iu);
    expect(parsed.body).toContain("skills/cure/SKILL.md");
  });

  // D5 — no auto-execute / no auto-chain on the command shim.
  it("commands/cure.md disclaims auto-execute / auto-chain (D5)", async () => {
    const source = await readSource("commands/cure.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/\bauto-execute\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-chain\b/iu);
  });

  // skills/cure/SKILL.md — frontmatter shape (name + owner).
  it("skills/cure/SKILL.md has cheese-flow skill frontmatter", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = parseSkillFrontmatter(parsed.data);

    expect(frontmatter.name).toBe("cure");
    expect(frontmatter.metadata?.owner).toBe("cheese-flow");
  });

  // §Approach — loop is `load → render table → user gate → apply → re-age`.
  it("skills/cure/SKILL.md describes the ordered loop phases", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    // Ordered phrasing: load before user gate before apply before re-age.
    const ordered = /load[\s\S]*user\s*gate[\s\S]*apply[\s\S]*re-?age/iu;
    expect(parsed.body).toMatch(ordered);
  });

  // D5 + D7 — user gate is the only path; default empty; no auto-execute.
  it("skills/cure/SKILL.md enforces the user gate, default empty, and disclaims auto-execute (D5/D7)", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/user\s*gate/iu);
    expect(parsed.body).toMatch(
      /default\s+(selection\s+)?(is\s+)?\*?\*?empty\*?\*?/iu,
    );
    expect(parsed.body).not.toMatch(/\bauto-execute\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-chain\b/iu);
  });

  // §Approach — cross-slice public skill seams.
  it("skills/cure/SKILL.md references the public skill seams it calls", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("/cleanup");
    expect(parsed.body).toContain("/age");
    expect(parsed.body).toContain("/cook");
  });

  // D3 — re-age cap = 3 turns; pin literal 3, deny drift to 2/4/5.
  it("skills/cure/SKILL.md hard-codes the literal cap of 3 turns (D3)", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    // Literal "3-turn", "cap = 3", or "turn < 3" must appear.
    expect(parsed.body).toMatch(
      /\b3-turn\b|\bcap\s*=\s*3\b|\bturn\s*<\s*3\b|\b3\s*turns?\s+per\b/iu,
    );
    // No drift to other small integers as the cap.
    expect(parsed.body).not.toMatch(/\bcap\s*=\s*[245]\b/iu);
    expect(parsed.body).not.toMatch(/\bturn\s*<\s*[245]\b/iu);
    expect(parsed.body).not.toMatch(/\b[245]-turn\b/iu);
  });

  // §User gate — verbs and empty default per spec.
  it("skills/cure/SKILL.md documents the user-gate verbs and empty default", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/\ball-high\b/u);
    expect(parsed.body).toMatch(/\bnone\b/u);
    expect(parsed.body).toMatch(/\bskip\s+\d|skip\s+N\b/u);
    expect(parsed.body).toMatch(
      /default\s+(selection\s+)?(is\s+)?\*?\*?empty\*?\*?/iu,
    );
  });

  // §Approach Entry — loads BOTH fixes.json AND suggestions.json and merges.
  it("skills/cure/SKILL.md loads fixes.json AND suggestions.json and merges into a unified table", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("fixes.json");
    expect(parsed.body).toContain("suggestions.json");
    expect(parsed.body).toMatch(/merge|unified|merged/iu);
  });

  // §sources adapter — sidecar paths and missing-sidecar error.
  it("references/sources.md documents sidecar paths and missing-sidecar error", async () => {
    const source = await readSource("skills/cure/references/sources.md");
    expect(source).toMatch(/\.cheese\/age\/[^`\s]*\.fixes\.json/u);
    expect(source).toContain("suggestions.json");
    // Missing-sidecar error language.
    expect(source).toMatch(/missing|error|not found/iu);
  });

  // §Apply router — apply-router.md maps every routing type to its handler.
  it("references/apply-router.md maps every routing type to its handler", async () => {
    const source = await readSource("skills/cure/references/apply-router.md");
    // edit → /cleanup
    expect(source).toMatch(/\bedit\b[\s\S]{0,80}\/cleanup/iu);
    // suggestion → cook sub-agent
    expect(source).toMatch(
      /\bsuggestion\b[\s\S]{0,120}cook[\s\S]{0,40}sub-?agent/iu,
    );
  });

  // §Re-age verify loop — 3-turn cap, /age --scope invocation, diff prior,
  // only new/changed items.
  it("references/re-age.md documents the 3-turn cap, /age --scope, and diff semantics", async () => {
    const source = await readSource("skills/cure/references/re-age.md");
    // Literal cap of 3.
    expect(source).toMatch(
      /\b3-turn\b|\bcap\s*=\s*3\b|\bturn\s*<\s*3\b|\b3\s*turns?\b/iu,
    );
    // No drift to other small integers as the cap.
    expect(source).not.toMatch(/\bcap\s*=\s*[245]\b/iu);
    expect(source).not.toMatch(/\bturn\s*<\s*[245]\b/iu);
    // /age --scope <touched_paths> invocation.
    expect(source).toMatch(/\/age\s+--scope/u);
    expect(source).toContain("touched_paths");
    // Diff against prior items.
    expect(source).toMatch(/\bdiff\b[\s\S]{0,80}\bprior\b/iu);
    // Only new/changed items advance.
    expect(source).toMatch(/\bnew\b\s+or\s+changed|only\s+new[/\s]/iu);
  });

  // §Re-age — turn-log file path per spec.
  it("references/re-age.md mentions the turn-log file path", async () => {
    const source = await readSource("skills/cure/references/re-age.md");
    expect(source).toMatch(/\.cheese\/cure\/[^`\s]*turns\.log\.json/u);
  });

  // commands/cure.md — argument-hint frontmatter pins the CLI surface (slug).
  it("commands/cure.md argument-hint pins <slug>", async () => {
    const source = await readSource("commands/cure.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);
    expect(command["argument-hint"]).toBeDefined();
    const hint = command["argument-hint"] ?? "";
    expect(hint).toContain("<slug>");
  });

  // §User gate — comma-separated id verb literally documented as "1,3,5".
  // Spec line: `1,3,5         (specific ids)`.
  it("skills/cure/SKILL.md pins the comma-separated specific-ids verb 1,3,5", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("1,3,5");
  });

  // §User gate — verb `skip N` literally uses the placeholder `N`.
  it("skills/cure/SKILL.md uses the literal `skip N` placeholder", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/\bskip\s+N\b/u);
  });

  // D2 — the unified-loop framing. Spec calls /cure the *single hand-off
  // target*; SKILL.md must echo single/finisher framing somewhere.
  it("skills/cure/SKILL.md frames /cure as the single post-/age finisher (D2)", async () => {
    const source = await readSource("skills/cure/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(
      /\bsingle\b[^\n]{0,40}(hand-?off\s+target|finisher)/iu,
    );
  });

  // D3 rationale — the spec explicitly flags the cap value for
  // post-implementation review and ties the turn log to that review. The
  // re-age reference must surface that rationale, not just the literal 3.
  it("references/re-age.md captures the post-implementation review flag for the cap (D3)", async () => {
    const source = await readSource("skills/cure/references/re-age.md");
    expect(source).toMatch(/post-?implementation\s+review/iu);
    // Turn-log purpose tied to tuning, per spec.
    expect(source).toMatch(/tune|tuning/iu);
  });

  // §Apply router — suggestion items spawn a cook sub-agent with the
  // `agent_brief_for_cook` payload. Pin the literal payload identifier.
  it("references/apply-router.md names the agent_brief_for_cook payload (D4)", async () => {
    const source = await readSource("skills/cure/references/apply-router.md");
    expect(source).toContain("agent_brief_for_cook");
  });
});
