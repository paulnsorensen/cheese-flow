---
name: nih-audit
description: Scan a codebase for custom code that duplicates what open-source libraries already do, then recommend which libraries to adopt. Detects hand-rolled utility functions, custom retry logic, manual validation, DIY date handling, home-grown argument parsers, and other reinvented wheels. Cross-checks against installed dependencies and open specs. Returns scored migration recommendations with effort estimates. Use when the user mentions reinventing the wheel, asks if there is a library for something they built, wants a build-vs-buy audit, asks "should we just use lodash for this", or wants to find dependency opportunities.
license: MIT
compatibility: Requires tilth MCP for AST-aware search. Library discovery delegates to /research; if /research is unavailable, the audit reports candidates without library recommendations.
metadata:
  owner: cheese-flow
  category: review
allowed-tools:
  - read
  - write
  - bash
  - subagent
  - mcp
---
# NIH Audit — Not Invented Here

Find code reinventing the wheel. Recommend libraries. Score with evidence.

`/nih-audit [scope]` — `scope` defaults to repo root.

This skill is the heavy whole-repo audit. The diff-scoped variant runs as the
`nih` dim inside `/age`. The lightweight pre-Sketch probe lives in `/mold`.
Use `/nih-audit` when you want a full sweep with library recommendations and
migration paths.

## Phase 0 — Manifest discovery (no LLM)

Find dependency manifests anywhere in scope, excluding `node_modules/`,
`vendor/`, `.git/`, build artefacts:

- `package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, `Gemfile`,
  `requirements.txt`, `composer.json`, `build.gradle`, `pom.xml`, `mix.exs`.

Extract dependency names per ecosystem:

| Manifest | Extract |
|----------|---------|
| `package.json` | `jq -r '(.dependencies + .devDependencies) // {} \| keys[]'` |
| `Cargo.toml` | parse `[dependencies]` table |
| `pyproject.toml` | `[project.dependencies]` or `[tool.poetry.dependencies]` |
| `go.mod` | `require` block module paths |
| `requirements.txt` | line-by-line package names |

Build a `depManifest`:

```json
{
  "workspaces": [
    { "root": ".", "ecosystem": "node", "deps": ["express", "zod"] }
  ],
  "primaryLanguages": ["typescript"]
}
```

If no manifest is found anywhere in scope, abort with a clear message —
without an installed-deps list there is nothing to cross-reference.

## Phase 1 — Structural NIH scan

Spawn the `nih-scanner` sub-agent (see `agents/nih-scanner.md.eta`):

```
inputs:
  languages   = primaryLanguages from Phase 0
  scope       = $ARGUMENTS or repo root
  depManifest = JSON from Phase 0
  slug        = <derived slug>
```

The scanner returns a JSON candidate list inline plus a one-paragraph
summary. Parse the candidates from the response. If 0 candidates, report
clean and stop.

## Phase 2 — Library discovery (parallel, /research)

Group candidates by `category` (RETRY, UUID, VALIDATION, DATE, DEBOUNCE,
CLONE, ARGPARSE, STRING, HTTP, SERIALIZATION, ERROR, CRYPTO, SECURITY,
FORMAT, COMPARE).

For each category, dispatch `/research` with a focused question shape:

```
/research "best <category> library for <language>; must be MIT/Apache/BSD;
list weekly downloads or crates.io downloads, GitHub stars, last commit
date, contributor count; flag if functionality is in the standard library"
```

Cap: max 5 parallel research dispatches. If `/research` is unavailable,
emit candidates with `recommendation: null` and a note.

For each library returned, capture:

- name + latest version
- license (flag GPL; prefer MIT/Apache-2.0/BSD)
- weekly/monthly download count
- GitHub stars, last commit date, contributor count
- whether it is stdlib, micro-library, or framework
- one-sentence API example showing replacement shape

Drop recommendations whose name is already in `depManifest`. Stdlib
alternatives (no new dep) are the highest-value class — keep them
prioritized.

See `references/categories.md` for the canonical category-to-library map.

## Phase 3 — Spec and intent alignment

Find spec directories within scope: `**/specs/*.md`, `.cheese/specs/*.md`.
Filter out `node_modules/`, `vendor/`, `.git/`.

For each candidate, look for signals that the NIH choice was deliberate:

- **In specs**: keywords like "intentionally", "we chose to build", "build
  vs buy", "don't use", "avoid dependency on" near the candidate's concept.
- **In the candidate file**: comments like `intentionally`, `deliberately`,
  `we chose`, `NOTE:`, `DECISION:`, `instead of`, `rather than`.

Apply scoring modifiers:

| Signal | Modifier |
|--------|----------|
| Spec explicitly chose NIH | -30 |
| Code comment explains NIH choice | -20 |
| Library covers planned spec features | +10 |

## Phase 4 — Score and synthesize

For every candidate with a library recommendation, run the 4-step
confidence chain:

### Step 1 — classify finding type

| Type | Base | Cap |
|------|------|-----|
| `REPLACE_WITH_STDLIB` | 55 | 100 |
| `REPLACE_WITH_MICRO_LIB` | 45 | 95 |
| `REPLACE_WITH_FRAMEWORK` | 35 | 85 |
| `EXTRACT_TO_EXISTING_DEP` | 50 | 95 |

### Step 2 — evidence grounding

| Evidence | Modifier |
|----------|----------|
| Caller count grounded in cheez-search | +15 |
| Library has >10K weekly downloads + permissive licence | +20 |
| ast-grep pattern + code read confirms NIH | +15 |
| NIH code has recent bug fixes (git log) | +10 |
| NIH code >100 LOC for what library does in 1 call | +10 |
| Generic pattern, code does more than pattern suggests | -15 |
| Library unmaintained (last commit >1 yr) | hard cap at 40 |

### Step 3 — context modifiers

Apply Phase 3 modifiers (spec intent, code comments, planned features) plus:

| Signal | Modifier |
|--------|----------|
| NIH code in git hotspot (many recent changes) | +10 |
| NIH code isolated (1 file, clear boundary) | +5 |
| NIH code deeply coupled (referenced from >10 files) | -5 |

### Step 4 — independent second pass

For every candidate, score independently from the first pass:

1. Drop the first score from working memory.
2. Re-read the NIH code and the library API fresh.
3. Score using Steps 1–3 again.
4. Report both scores in the finding.
5. Final score = average of pass 1 and pass 2.
6. Divergence > 20 points → tag `AMBIGUOUS`, still emit.

### Effort sizing

| Criteria | Size |
|----------|------|
| 1 file, <50 LOC, ≤3 call sites | S |
| 2-5 files, <200 LOC, ≤10 call sites | M |
| >5 files, >200 LOC, or >10 call sites | L |

## Phase 5 — Report

Write the full report to `.cheese/nih/<slug>.md`. Render every candidate
above the threshold; do not silently filter. Each finding follows the
template in `references/finding-template.md`:

```markdown
### Finding #N: <title> (Score: NN) [AMBIGUOUS if passes diverge >20]

**NIH Code**: `path/to/file.ts:line-line` (N LOC)
**Category**: CATEGORY
**Pattern**: <what was detected>

**Recommended Alternative**: `library-name@version`
- Licence: MIT/Apache-2.0/BSD
- Downloads: N/week | Stars: N | Last commit: YYYY-MM-DD
- Contributors: N

**Code Touchpoints**:
- `path:line` — implementation (DELETE or REPLACE)
- `path:line` — import (UPDATE)

**Effort**: S | M | L (N files, N call sites)

**Migration**:
1. Install: `npm install ...` / `cargo add ...`
2. Replace: <specific change>
3. Clean up: <removed files/tests>

**Scoring**:
- Pass 1: NN (base NN + evidence NN + context NN)
- Pass 2: NN
- Final: NN (average)

**Why do it**: <maintenance burden, upstream bugs fixed, stdlib means zero
deps, covers planned features, ...>

**Why not**: <trivial code not worth a dep, hot path needing control,
intentional design choice, transitive dep risk, ...>
```

Top of the report:

```markdown
# NIH Audit — <scope>

## Summary
- Files scanned: N
- Candidates found: N
- Already using best option: N (filtered)
- Ambiguous (passes diverge >20): N

## All findings (sorted by score, descending)

| # | Score | P1 | P2 | Category | NIH Code | Replace With | Effort |
|---|-------|----|----|----------|----------|--------------|--------|
| 1 | 92 | 90 | 94 | UUID | src/utils/uuid.ts:12 | crypto.randomUUID() (stdlib) | S |
```

After the table, render every `### Finding #N` block inline.

## Phase 6 — Hand-off

Print the report path. Do not auto-invoke any follow-up:

```
NIH report: .cheese/nih/<slug>.md

Next steps (manual):
  • Pick the highest-scored finding and migrate.
  • For S-effort stdlib swaps, /cook is usually the right next step.
  • For L-effort framework swaps, run /mold first to lock down the
    migration interface.
```

## Rules

- Do not modify code or implement migrations — recommend; the human decides.
- Do not recommend GPL libraries without flagging the licence risk.
- Do not override explicit NIH decisions documented in specs or code
  comments — apply the scoring modifiers and surface the conflict.
- Do not run in scopes without any manifest file — there is nothing to
  cross-reference.
- Empty results report clean and stop. Never force findings.
- Cap total tool calls across all phases at ~60. After the cap, synthesize
  from available data and note incomplete coverage.

## Gotchas

- **ast-grep patterns are approximate.** A `clearTimeout` + `setTimeout`
  combo isn't always a debounce. Step 2's "generic pattern, code does
  more" modifier (-15) catches false positives.
- **Stdlib alternatives are the highest value.** `crypto.randomUUID()`
  replacing a hand-rolled UUID is a no-brainer. Always score these
  highest (REPLACE_WITH_STDLIB, base 55, cap 100).
- **Already-installed is the most common false positive.** A codebase
  that has lodash but hand-rolls `deepClone` may have done so for bundle
  size reasons. The spec/comment check (Phase 3) catches this.
- **Monorepo dep scoping.** A function in `packages/api/` may be NIH in
  that workspace but the library is installed in `packages/web/`. Each
  workspace's `depManifest` is independent.
- **Licence compatibility is not just MIT-vs-GPL.** Some projects have
  specific licence requirements. When in doubt, flag the licence and let
  the human decide.
