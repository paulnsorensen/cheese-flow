import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseFrontmatter } from "../src/lib/frontmatter.js";
import {
  parseAgentFrontmatter,
  parseCommandFrontmatter,
  parseSkillFrontmatter,
} from "../src/lib/schemas.js";

const root = path.resolve(".");

async function readSource(relativePath: string): Promise<string> {
  return readFile(path.join(root, relativePath), "utf8");
}

describe("Fromage TDD flow artifacts", () => {
  it("ships a focused fromage command without batching or fleet language", async () => {
    const source = await readSource("commands/fromage.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);

    expect(command.name).toBe("fromage");
    expect(parsed.body).toContain("Cut → Cook → Press");
    expect(parsed.body).toContain("Cheez skills");
    expect(parsed.body).not.toMatch(
      /\b(batch|batching|fleet|parallel worktree)\b/iu,
    );
  });

  it("binds cut, cook, and press agents to Cheez and TDD skills", async () => {
    for (const agent of ["fromage-cut", "fromage-cook", "fromage-press"]) {
      const source = await readSource(`agents/${agent}.md.eta`);
      const parsed = parseFrontmatter<unknown>(source);
      const frontmatter = parseAgentFrontmatter(parsed.data);

      expect(frontmatter.skills).toEqual(
        expect.arrayContaining([
          "cheez-read",
          "cheez-search",
          "cheez-write",
          "test-driven-development",
        ]),
      );
      expect(parsed.body).toContain("Self-evaluation checklist");
    }
  });

  it("attributes the copied and modified Superpowers TDD skill", async () => {
    const source = await readSource("skills/test-driven-development/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    const skill = parseSkillFrontmatter(parsed.data);

    expect(skill.name).toBe("test-driven-development");
    expect(parsed.body).toContain(
      "https://github.com/obra/superpowers/tree/main/skills/test-driven-development",
    );
    expect(parsed.body).toContain(
      "No production code without a failing test first",
    );
    expect(parsed.body).toContain("Self-evaluation checklist");
  });
});
