import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseFrontmatter } from "../src/lib/frontmatter.js";
import {
  parseAgentFrontmatter,
  parseCommandFrontmatter,
} from "../src/lib/schemas.js";

const root = path.resolve(".");

async function readSource(relativePath: string): Promise<string> {
  return readFile(path.join(root, relativePath), "utf8");
}

describe("/cook flow artifacts", () => {
  it("ships a focused cook command without batching or fleet language", async () => {
    const source = await readSource("commands/cook.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);

    expect(command.name).toBe("cook");
    expect(parsed.body).toContain("cut → cook → press");
    expect(parsed.body).toContain("Cheez skills");
    expect(parsed.body).not.toMatch(
      /\b(batch|batching|fleet|parallel worktree)\b/iu,
    );
    expect(parsed.body).not.toMatch(/\bfromage\b/iu);
  });

  it("binds cut, cook, press, and assertion-review to the Cheez skills", async () => {
    for (const agent of ["cut", "cook", "press", "assertion-review"]) {
      const source = await readSource(`agents/${agent}.md.eta`);
      const parsed = parseFrontmatter<unknown>(source);
      const frontmatter = parseAgentFrontmatter(parsed.data);

      expect(frontmatter.skills).toEqual(
        expect.arrayContaining(["cheez-read", "cheez-search"]),
      );
      expect(frontmatter.skills).not.toContain("test-driven-development");
      expect(parsed.body).toContain("Self-evaluation checklist");
    }
  });

  it("inlines the TDD core rule in cut and cook agent bodies", async () => {
    const cut = await readSource("agents/cut.md.eta");
    expect(cut).toContain("No production code without a failing test first");

    const cook = await readSource("agents/cook.md.eta");
    expect(cook).toContain("Red → Green → Refactor");
  });

  it("declares assertion-review as a spec-drift detector with a scoring rubric", async () => {
    const source = await readSource("agents/assertion-review.md.eta");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = parseAgentFrontmatter(parsed.data);

    expect(frontmatter.name).toBe("assertion-review");
    expect(parsed.body).toContain("Spec-drift rubric");
    expect(parsed.body).toContain("STRONG");
    expect(parsed.body).toContain("MISSING");
    expect(parsed.body).toContain("CONTRADICTS");
  });

  it("wires /cook into the /cheese routing table", async () => {
    const source = await readSource("commands/cheese.md");
    expect(source).toContain("`/cook`");
    expect(source).not.toMatch(/`\/fromage`/u);
  });
});
