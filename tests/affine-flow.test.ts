import { readFile, stat } from "node:fs/promises";
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

async function pathExists(relativePath: string): Promise<boolean> {
  try {
    await stat(path.join(root, relativePath));
    return true;
  } catch {
    return false;
  }
}

describe("/affine flow artifacts (revised: collector + classifier only)", () => {
  // commands/affine.md — D1 (name), §Slice (points at skills/affine/SKILL.md).
  it("ships a thin /affine command shim that points at the skill", async () => {
    const source = await readSource("commands/affine.md");
    const parsed = parseFrontmatter<unknown>(source);
    const command = parseCommandFrontmatter(parsed.data);

    expect(command.name).toBe("affine");
    expect(command.description).toMatch(/(collect|classif|sidecar|ingest)/iu);
    // Body lists the revised loop phases and routes to the skill.
    expect(parsed.body).toMatch(/collect/iu);
    expect(parsed.body).toMatch(/classify/iu);
    expect(parsed.body).toMatch(/emit|sidecar/iu);
    expect(parsed.body).toMatch(/hand-?off|\/cure/iu);
    expect(parsed.body).toContain("skills/affine/SKILL.md");
  });

  // D4 — no auto-execute / no auto-reply / no auto-post on the command shim.
  it("commands/affine.md disclaims auto-execute / auto-reply / auto-post (D4)", async () => {
    const source = await readSource("commands/affine.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/\bauto-execute\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-reply\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-post\b/iu);
  });

  // D8 — --age mode dropped from the command shim. Consuming /age sidecars
  // moved to /cure --from age <slug>.
  it("commands/affine.md drops the --age mode (D8)", async () => {
    const source = await readSource("commands/affine.md");
    expect(source).not.toMatch(/--age\b/u);
  });

  // skills/affine/SKILL.md — frontmatter shape (name + owner).
  it("skills/affine/SKILL.md has cheese-flow skill frontmatter", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    const frontmatter = parseSkillFrontmatter(parsed.data);

    expect(frontmatter.name).toBe("affine");
    expect(frontmatter.metadata?.owner).toBe("cheese-flow");
  });

  // §Approach — revised loop: collect → classify → emit → hand off to /cure.
  // Apply, user gate, re-age all moved to /cure (D6).
  it("skills/affine/SKILL.md describes the revised collector loop (D6)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    const ordered =
      /collect[\s\S]*classify[\s\S]*(emit|sidecar)[\s\S]*(hand-?off|\/cure)/iu;
    expect(parsed.body).toMatch(ordered);
  });

  // D6 — /affine does NOT own user gate, apply, or re-age. These belong to
  // /cure. The skill must not document any of those phases as its own.
  it("skills/affine/SKILL.md does not own user-gate / apply / re-age phases (D6)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/##\s*Phase\s*\d[^\n]*user\s*gate/iu);
    expect(parsed.body).not.toMatch(/##\s*Phase\s*\d[^\n]*apply/iu);
    expect(parsed.body).not.toMatch(/##\s*Phase\s*\d[^\n]*re-?age/iu);
  });

  // D6 — /affine does NOT invoke /age itself. The 3-turn cap belongs to /cure.
  it("skills/affine/SKILL.md does not document a turn cap (D6, moved to /cure)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/\bcap\s*=\s*3\b/iu);
    expect(parsed.body).not.toMatch(/\bturn\s*<\s*3\b/iu);
    expect(parsed.body).not.toMatch(/\b3-turn\s+cap\b/iu);
    expect(parsed.body).not.toMatch(/\b3\s+turns?\s+per\b/iu);
  });

  // §Approach Entry — auto-detect from PR or manual only. /age sidecar branch
  // dropped (D8).
  it("skills/affine/SKILL.md auto-detects PR / manual only — no /age branch (D8)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/\bauto-?detect\b/iu);
    expect(parsed.body).toMatch(/open\s+PR|PR\s+(present|exists|on)/iu);
    expect(parsed.body).toMatch(/manual/iu);
    // The legacy "/age sidecar" auto-detect branch is gone; the SKILL must not
    // tell users to consume .cheese/age/<slug>.fixes.json — that's /cure's job.
    expect(parsed.body).not.toMatch(/\.cheese\/age\/[^`\s]*\.fixes/u);
  });

  // D8 — argument forms: --from <pr>, --manual, auto-detect. No --age.
  it("skills/affine/SKILL.md documents three argument forms (no --age) (D8)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("--from");
    expect(parsed.body).toContain("--manual");
    expect(parsed.body).toMatch(/auto-?detect/iu);
    // --age mode is dropped per D8.
    expect(parsed.body).not.toMatch(/--age\b/u);
  });

  // D4 + D7 — hand-off line is literally `Run /cure --from affine <slug>`,
  // pinned verbatim so /cure autocomplete and docs stay consistent.
  it("skills/affine/SKILL.md prints the literal /cure --from affine handoff (D4/D7)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/Run\s+\/cure\s+--from\s+affine\s+<slug>/u);
  });

  // D4 — no auto-execute / no auto-reply / no auto-post on the skill.
  it("skills/affine/SKILL.md disclaims auto-actions (D4)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/\bauto-execute\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-reply\b/iu);
    expect(parsed.body).not.toMatch(/\bauto-post\b/iu);
  });

  // D7 — Sliced Bread crust: /affine's only cross-slice hand-off is /cure via
  // the v2 sidecar + the printed handoff. /affine does NOT internally invoke
  // /cleanup or /merge-resolve — those are /cure's apply-router targets.
  it("skills/affine/SKILL.md does not internally invoke apply handlers (D7)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    // The hand-off goes to /cure.
    expect(parsed.body).toContain("/cure");
    // Apply-handler cross-calls belong to /cure, not /affine.
    expect(parsed.body).not.toMatch(/\/cleanup\b/u);
    expect(parsed.body).not.toMatch(/\/merge-resolve\b/u);
  });

  // D4 — /affine emits its sidecar to .cheese/affine/<slug>.fixes.json. The
  // exact path is the cross-slice contract /cure consumes.
  it("skills/affine/SKILL.md emits to .cheese/affine/<slug>.fixes.json", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/\.cheese\/affine\/[^`\s]*\.fixes\.json/u);
  });

  // D4 — replies are no longer drafted by /affine. The replies file moved to
  // /cure (.cheese/cure/<slug>.replies.md). /affine emits category=reply items
  // into the sidecar but never drafts to a file or posts.
  it("skills/affine/SKILL.md does not own the replies file (moved to /cure)", async () => {
    const source = await readSource("skills/affine/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).not.toMatch(/\.cheese\/affine\/[^`\s]*replies\.md/u);
    expect(parsed.body).not.toMatch(/##\s*Replies\s+file/iu);
  });

  // §Source adapters — sources.md covers PR + manual adapters and folds
  // CI failures and merge conflicts into the PR change-order (D5).
  it("references/sources.md documents PR / manual adapters and folds CI + merge into the PR change-order (D5)", async () => {
    const source = await readSource("skills/affine/references/sources.md");
    expect(source).toMatch(/from_pr\b|PR adapter|source\s*=\s*pr/iu);
    expect(source).toMatch(
      /from_manual\b|manual adapter|source\s*=\s*manual/iu,
    );
    expect(source).toMatch(/category\s*=\s*ci_fix|\bci_fix\b/u);
    expect(source).toMatch(/category\s*=\s*merge_fix|\bmerge_fix\b/u);
  });

  // D8 — sources.md drops the from_age adapter. Consuming /age sidecars is
  // /cure --from age <slug>'s job.
  it("references/sources.md does not document a from_age adapter (D8)", async () => {
    const source = await readSource("skills/affine/references/sources.md");
    expect(source).not.toMatch(/from_age\b/u);
    expect(source).not.toMatch(/age adapter/iu);
    expect(source).not.toMatch(/source\s*=\s*age\b/iu);
  });

  // §Schema — schema.md documents v2 additive fields and preserves v1
  // required keys. Schema is shared with /age, /cleanup, /cure.
  it("references/schema.md documents the v2 additive sidecar fields", async () => {
    const source = await readSource("skills/affine/references/schema.md");
    // v2 additive fields
    expect(source).toContain("pr_thread_id");
    expect(source).toContain("review_body_id");
    expect(source).toContain("reviewer");
    expect(source).toContain("job_id");
    expect(source).toContain("log_excerpt");
    expect(source).toContain("conflicting_paths");
    // v1 required keys are still required
    for (const key of [
      "id",
      "dimension",
      "file",
      "anchor",
      "content",
      "rationale",
      "category",
    ]) {
      expect(source).toContain(key);
    }
    // Explicitly notes additive / unchanged contract.
    expect(source).toMatch(/additive|unchanged|no breaking change/iu);
  });

  // §Stake-weighted classify — classify.md inputs, rollup buckets, hard rules.
  it("references/classify.md documents stake-weighted rollup with required constraints", async () => {
    const source = await readSource("skills/affine/references/classify.md");
    expect(source).toMatch(/\bseverity\b/iu);
    expect(source).toMatch(/\bblast\b/iu);
    expect(source).toMatch(/\bconsensus\b/iu);
    expect(source).toMatch(/\bhigh\b[\s\S]*\bmedium\b[\s\S]*\blow\b/iu);
    // Constraint: build/merge always high.
    expect(source).toMatch(
      /(build|merge)[\s\S]{0,60}\balways\b[\s\S]{0,40}\bhigh\b/iu,
    );
    // Constraint: pure style never high.
    expect(source).toMatch(/style[\s\S]{0,40}\bnever\b[\s\S]{0,40}\bhigh\b/iu);
    // Constraint: CHANGES_REQUESTED w/o code reference cannot exceed medium.
    expect(source).toMatch(/CHANGES_REQUESTED/u);
    expect(source).toMatch(
      /CHANGES_REQUESTED[\s\S]*\bmedium\b|cannot exceed medium/iu,
    );
  });

  // §Schema + D2 — /cleanup tolerates v2 additive entries while keeping v1 required.
  it("skills/cleanup/SKILL.md tolerates v2 additive sidecar fields (D2)", async () => {
    const source = await readSource("skills/cleanup/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    // v1 hard-error preserved: aborts on missing required fields.
    expect(parsed.body).toMatch(/abort/iu);
    for (const key of [
      "id",
      "dimension",
      "file",
      "anchor",
      "content",
      "rationale",
      "category",
    ]) {
      expect(parsed.body).toContain(key);
    }
    // New v2 tolerance language: additional / optional fields tolerated.
    expect(parsed.body).toMatch(
      /(additional|optional|extra)\s+(fields|keys|properties)[\s\S]{0,80}(tolerat|accept|ignor|allow)/iu,
    );
    expect(parsed.body).toMatch(/additive|v2/iu);
  });

  // §Non-goals — branch rescue without a PR is /move-my-cheese, not /affine.
  it("commands/affine.md disclaims branch rescue (defers to /move-my-cheese)", async () => {
    const source = await readSource("commands/affine.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("/move-my-cheese");
  });

  // D3 — stake-weighted, NOT 0-100 categorical. The negation: no numeric
  // confidence scale should appear in user-facing classify documentation.
  it("references/classify.md uses stake buckets only — no 0-100 numeric scoring (D3)", async () => {
    const source = await readSource("skills/affine/references/classify.md");
    expect(source).not.toMatch(/\b0\s*[-–to]+\s*100\b/iu);
    expect(source).toMatch(/no\s+numbers|no\s+numeric/iu);
  });

  // D6 — apply-router moved to /cure. The legacy file under skills/affine/
  // must NOT exist; cure's apply-router is the only one.
  it("skills/affine/references/apply-router.md does not exist (apply moved to /cure)", async () => {
    const exists = await pathExists("skills/affine/references/apply-router.md");
    expect(exists).toBe(false);
  });

  it("skills/cure/references/apply-router.md exists (apply lives in /cure)", async () => {
    const exists = await pathExists("skills/cure/references/apply-router.md");
    expect(exists).toBe(true);
  });

  // §Schema — literal `version: 2` and the source enum.
  it("references/schema.md pins version: 2 and the source enum literally", async () => {
    const source = await readSource("skills/affine/references/schema.md");
    expect(source).toMatch(/"version"\s*:\s*2\b/u);
    // Shared schema documents both /age- and /affine-emitted sidecars; enum
    // contains all three values.
    expect(source).toMatch(/age\s*\|\s*pr\s*\|\s*manual/u);
  });

  // §Schema — file locations differ between /age and /affine emitters.
  it("references/schema.md documents both sidecar paths (/age and /affine)", async () => {
    const source = await readSource("skills/affine/references/schema.md");
    expect(source).toMatch(/\.cheese\/age\/[^`\s]*\.fixes\.json/u);
    expect(source).toMatch(/\.cheese\/affine\/[^`\s]*\.fixes\.json/u);
  });

  // §Source adapters — from_pr enforces !is_resolved && !is_outdated for threads.
  it("references/sources.md filters out resolved/outdated PR threads", async () => {
    const source = await readSource("skills/affine/references/sources.md");
    expect(source).toMatch(/!is_resolved/u);
    expect(source).toMatch(/!is_outdated/u);
  });

  // §Source adapters — merge_items_for activates only when mergeable_state == "dirty".
  it("references/sources.md gates merge_items_for on mergeable_state == 'dirty'", async () => {
    const source = await readSource("skills/affine/references/sources.md");
    expect(source).toMatch(/mergeable_state\s*[!=]=\s*"dirty"/u);
  });

  // §Source adapters — ci_items_for filters on conclusion=failure.
  it("references/sources.md filters CI runs on conclusion=failure", async () => {
    const source = await readSource("skills/affine/references/sources.md");
    expect(source).toMatch(/conclusion\s*=\s*"?failure"?/u);
  });

  // commands/affine.md routes the hand-off to /cure (user-facing alignment).
  it("commands/affine.md routes the hand-off to /cure", async () => {
    const source = await readSource("commands/affine.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toContain("/cure");
  });
});

describe("/age Phase 4 hand-off (collapsed to /cure)", () => {
  // Bundled with the /affine revision: collapse the legacy two-line menu
  // (`/cleanup <slug>` + `/fromage cook --suggestions <slug>`) into a single
  // `/cure <slug>` hand-off. /cure now consumes both fixes.json and
  // suggestions.json in one pass, so the split menu is redundant.
  it("skills/age/SKILL.md hands off to /cure (single-line menu)", async () => {
    const source = await readSource("skills/age/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(/\/cure\s+<slug>/u);
  });

  it("skills/age/SKILL.md drops the legacy two-line cleanup/cook-suggestions menu", async () => {
    const source = await readSource("skills/age/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    // The two-line menu offered /cleanup and /fromage cook --suggestions as
    // separate next steps. After collapse, neither bullet should remain in the
    // hand-off section.
    expect(parsed.body).not.toMatch(/\/cleanup\s+<slug>/u);
    expect(parsed.body).not.toMatch(/\/fromage\s+cook\s+--suggestions/u);
  });

  // D-14-final still applies: the report is the deliverable; /cure is not
  // auto-invoked.
  it("skills/age/SKILL.md does not auto-invoke /cure", async () => {
    const source = await readSource("skills/age/SKILL.md");
    const parsed = parseFrontmatter<unknown>(source);
    expect(parsed.body).toMatch(
      /(do\s+not\s+auto-invoke|no\s+auto-invoke|never\s+auto-invoke)/iu,
    );
  });
});
