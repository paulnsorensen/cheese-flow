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

const DIMS = [
  "activation",
  "tool-scoping",
  "context",
  "prompt-quality",
  "output-format",
] as const;

const STAKE_BY_DIM: Record<(typeof DIMS)[number], "high" | "medium"> = {
  activation: "high",
  "tool-scoping": "high",
  context: "medium",
  "prompt-quality": "medium",
  "output-format": "medium",
};

const FIXTURE_STAKE_BY_DIM: Record<(typeof DIMS)[number], "high" | "medium"> = {
  ...STAKE_BY_DIM,
};

const FIXTURE_BUCKET_BY_DIM: Record<(typeof DIMS)[number], "high" | "med"> = {
  activation: "high",
  "tool-scoping": "high",
  context: "med",
  "prompt-quality": "med",
  "output-format": "med",
};

const FIXTURE_NARRATIVE_KEYWORDS: Record<(typeof DIMS)[number], RegExp> = {
  activation: /trigger|summary|routing|description/iu,
  "tool-scoping": /read-only|disallowedTools|Edit|tilth_edit/u,
  context: /fork|output|budget|unbounded|verbose/iu,
  "prompt-quality": /calibration|scaffold|rubric|judgment/iu,
  "output-format": /summary|table|structured|temp file|pointer/iu,
};

async function readSource(relativePath: string): Promise<string> {
  return readFile(path.join(root, relativePath), "utf8");
}

describe("/skill-improver command shim", () => {
  it("ships commands/skill-improver.md as a slim shim that delegates to the skill", async () => {
    const source = await readSource("commands/skill-improver.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);

    expect(command.name).toBe("skill-improver");
    expect(parsed.body).toContain(
      "Invoke the `skill-improver` skill with `$ARGUMENTS`",
    );
  });

  it("lists all five dimensions in the command body", async () => {
    const source = await readSource("commands/skill-improver.md");
    for (const dim of DIMS) {
      expect(source).toContain(dim);
    }
  });

  it("declares the amplifier-pure boundary (no writes) in the command body", async () => {
    const source = await readSource("commands/skill-improver.md");
    expect(source).toMatch(/no writes/iu);
  });
});

describe("/skill-improver skill orchestrator", () => {
  it("ships skills/skill-improver/SKILL.md with the skill name", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    const skill = parseSkillFrontmatter(parsed.data);

    expect(skill.name).toBe("skill-improver");
  });

  it("mentions all five dim names in the orchestrator body", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    for (const dim of DIMS) {
      expect(source).toContain(dim);
    }
  });

  it("references reuse of /cleanup and cleanup-wolf rather than new cleanup machinery", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    expect(source).toContain("/cleanup");
    expect(source).toContain("cleanup-wolf");
  });

  it("references the shared sidecar schema (fixes.json and suggestions.json)", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    expect(source).toContain("fixes.json");
    expect(source).toContain("suggestions.json");
  });

  it("declares the Claude Code >= 2.1.30 / claude-agent-sdk >= 0.2.63 compatibility gate", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    expect(source).toContain("2.1.30");
    expect(source).toContain("0.2.63");
  });
});

describe("/skill-improver dim agents", () => {
  for (const dim of DIMS) {
    it(`ships agents/skill-improver-${dim}.md.eta with the correct frontmatter contract`, async () => {
      const source = await readSource(`agents/skill-improver-${dim}.md.eta`);
      const parsed = parseFrontmatter<unknown>(source);
      const frontmatter = parseAgentFrontmatter(parsed.data);

      expect(frontmatter.name).toBe(`skill-improver-${dim}`);
      expect(frontmatter.models.default).toBe("claude-haiku-4-5");
      expect(frontmatter.tools).toEqual([
        "mcp__tilth__tilth_read",
        "mcp__tilth__tilth_search",
      ]);
      expect(frontmatter.skills).toEqual(
        expect.arrayContaining(["cheez-read", "cheez-search"]),
      );
      expect(frontmatter.metadata).toBeDefined();
      expect(frontmatter.metadata?.dim).toBe(dim);
      expect(frontmatter.metadata?.stake).toBe(STAKE_BY_DIM[dim]);
      expect(frontmatter.metadata?.intent).toBe("review");
      expect(frontmatter.metadata?.owner).toBe("cheese-flow");
    });

    it(`states the per-agent return contract ($RUN_DIR/${dim}.json) in the body`, async () => {
      const source = await readSource(`agents/skill-improver-${dim}.md.eta`);
      const parsed = parseFrontmatter<unknown>(source);
      expect(parsed.body).toContain(`$RUN_DIR/${dim}.json`);
    });
  }
});

describe("/skill-improver fixture targets", () => {
  for (const dim of DIMS) {
    it(`seeds expected.json with a finding bucketed at ${FIXTURE_BUCKET_BY_DIM[dim]} matching the dim's rubric`, async () => {
      const source = await readSource(
        `tests/skill-improver-fixtures/${dim}/expected.json`,
      );
      const parsed = JSON.parse(source) as {
        dimension: string;
        stake?: string;
        observations: Array<{
          id: string;
          bucket: string;
          narrative: string;
          anchor: { start: string };
        }>;
      };

      expect(parsed.dimension).toBe(dim);
      expect(parsed.stake).toBe(FIXTURE_STAKE_BY_DIM[dim]);
      expect(parsed.observations.length).toBeGreaterThanOrEqual(1);

      const first = parsed.observations[0];
      if (!first) throw new Error("expected at least one observation");

      expect(first.id).toBe(`${dim}-1`);
      expect(first.bucket).toBe(FIXTURE_BUCKET_BY_DIM[dim]);
      expect(first.narrative).toMatch(FIXTURE_NARRATIVE_KEYWORDS[dim]);
      expect(first.anchor.start).toMatch(/^\d+:[0-9a-f]+$/u);
    });

    it(`seeds target.md.eta with parseable agent frontmatter that exercises the ${dim} dim`, async () => {
      const source = await readSource(
        `tests/skill-improver-fixtures/${dim}/target.md.eta`,
      );
      const parsed = parseFrontmatter<unknown>(source);
      const frontmatter = parseAgentFrontmatter(parsed.data);

      expect(frontmatter.name.length).toBeGreaterThan(0);
      expect(frontmatter.description.length).toBeGreaterThan(0);
      expect(parsed.body.length).toBeGreaterThan(0);
    });
  }
});

describe("/skill-improver reference files", () => {
  it("ships skills/skill-improver/references/report-template.md", async () => {
    const source = await readSource(
      "skills/skill-improver/references/report-template.md",
    );
    expect(source).toContain("Skill-Improver Review");
    expect(source).toMatch(/orientation/iu);
    expect(source).toContain("Cross-dimension callouts");
  });

  it("ships skills/skill-improver/references/fixture-protocol.md", async () => {
    const source = await readSource(
      "skills/skill-improver/references/fixture-protocol.md",
    );
    expect(source).toContain("age_fixture_diff.py");
    expect(source).toContain("expected.json");
    expect(source).toContain("target.md.eta");
  });

  for (const dim of DIMS) {
    it(`ships skills/skill-improver/references/${dim}/protocol.md`, async () => {
      const source = await readSource(
        `skills/skill-improver/references/${dim}/protocol.md`,
      );
      expect(source.length).toBeGreaterThan(200);
      expect(source).toContain(dim);
    });
  }
});

describe("/skill-improver amplifier-pure boundary", () => {
  it("does not document a --fix flag in SKILL.md (FR-8: no auto-apply)", async () => {
    const source = await readSource("skills/skill-improver/SKILL.md");
    expect(source).not.toMatch(/--fix\b/u);
  });

  it("does not document a --fix flag in commands/skill-improver.md", async () => {
    const source = await readSource("commands/skill-improver.md");
    expect(source).not.toMatch(/--fix\b/u);
  });

  for (const dim of DIMS) {
    it(`agents/skill-improver-${dim}.md.eta documents fix as a {category, content} object, not a string`, async () => {
      const source = await readSource(`agents/skill-improver-${dim}.md.eta`);
      expect(source).toContain('"fix"');
      expect(source).toMatch(/"category"\s*:/u);
      expect(source).toMatch(/"content"\s*:/u);
    });
  }
});

describe("/skill-improver routing", () => {
  it("is mentioned in the /cheese routing table", async () => {
    const source = await readSource("commands/cheese.md");
    expect(source).toContain("/skill-improver");
  });
});

describe("/skill-improver justfile recipe", () => {
  it("declares a test-skill-improver-fixtures recipe", async () => {
    const source = await readSource("justfile");
    expect(source).toMatch(/^test-skill-improver-fixtures:/mu);
  });

  it("reuses python python/tools/age_fixture_diff.py as the comparator", async () => {
    const source = await readSource("justfile");
    const recipeMatch = source.match(
      /test-skill-improver-fixtures:[\s\S]*?(?=\n[a-zA-Z][a-zA-Z0-9_-]*[: ]|\n#|$)/u,
    );
    expect(recipeMatch).not.toBeNull();
    const recipe = recipeMatch?.[0] ?? "";
    expect(recipe).toContain("python python/tools/age_fixture_diff.py");
  });

  it("iterates the tests/skill-improver-fixtures/*/ directories", async () => {
    const source = await readSource("justfile");
    const recipeMatch = source.match(
      /test-skill-improver-fixtures:[\s\S]*?(?=\n[a-zA-Z][a-zA-Z0-9_-]*[: ]|\n#|$)/u,
    );
    expect(recipeMatch).not.toBeNull();
    const recipe = recipeMatch?.[0] ?? "";
    expect(recipe).toContain("tests/skill-improver-fixtures");
  });
});
