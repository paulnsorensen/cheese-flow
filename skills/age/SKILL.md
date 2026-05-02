---
name: age
description: Staff Engineer code review orchestrator. Runs eight orthogonal LLM dimensions over a diff and emits a stake-weighted report plus hash-anchored sidecar JSON.
license: MIT
compatibility: Requires Claude Code >= 2.1.30 / claude-agent-sdk >= 0.2.63 (older versions cannot expose tilth tools to plugin sub-agents).
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
# Age — Staff Engineer Code Review

Amplify the human reviewer's attention. Surface evidence, unknowns, and
tradeoffs. Do not render verdicts.

## Compatibility Check

Before dispatching agents, verify `tilth_*` MCP tools are available to
plugin sub-agents. If unavailable, fail fast:

```
ERROR: tilth MCP tools are not exposed to sub-agents.
Upgrade to Claude Code >= 2.1.30 / claude-agent-sdk >= 0.2.63.
See: anthropics/claude-code#13605
```

Do not attempt graceful degradation. The dim agents require `tilth_read`
and `tilth_search`; without them every agent silently misses evidence.

## Always-Fire Rationale (D-32)

All 8 dims fire on every invocation. Gating by file-type heuristics risks
silent misses. Each agent self-noops with `scope_match: false` + empty
observations when its rubric does not apply. Empty dims are tallied ("ran
8; N had findings"); only non-empty dims render as report sections.

Cost: ~30-40K Haiku tokens per /age. This is intentional and acceptable
(see spec D-32, D-21-final).

## Arguments

```
/age [<ref>] [--scope <path>] [--comprehensive]
```

- `ref` — git ref or range. Default: `$(git merge-base origin/main HEAD)..HEAD`
- `--scope <path>` — restrict evidence fetch to this path prefix
- `--comprehensive` — pass-through hint to dim agents; they may widen review window

## Phase 0 — Classify (no LLM)

Parse argv: extract `ref`, `scope`, `comprehensive` flag.

```bash
REF="${1:-$(git merge-base origin/main HEAD)..HEAD}"
SLUG="$(echo "$REF" | tr '/..:' '----' | head -c 32)"
RUN_DIR="${TMPDIR:-/tmp}/cheese-flow-age-$(date +%Y%m%d-%H%M%S)-${SLUG}"
mkdir -p "$RUN_DIR"
```

## Phase 1 — Pre-fetch Evidence (parallel; D-22)

Run all fetches in parallel. Merge into `$RUN_DIR/evidence-pack.yaml`.

**Parallel tasks:**

```bash
git diff --unified=3 $REF > $RUN_DIR/diff.patch
python python/tools/git_diagnose.py precedent \
  --symbols <touched-symbols> --paths <touched-paths> \
  > $RUN_DIR/precedent.json
python python/tools/git_diagnose.py concurrent-prs \
  --paths <touched-paths> \
  > $RUN_DIR/concurrent-prs.json
```

For each file touched by the diff:
- `cheez-read` in outline mode → file structure without inline source
- `tilth_deps` → import/export graph
- `cheez-search --kind callers` for each touched symbol

**Optional — code-review-graph impact radius:**

Try `get_impact_radius_tool(touched_symbols)`. If the MCP tool is
unavailable (plugin not loaded, tool not found), write:

```json
{"impact_radius": null}
```

and continue. Do NOT fail the run. Log a one-line notice.

**Merge into evidence pack:**

```yaml
# $RUN_DIR/evidence-pack.yaml
ref: <REF>
outlines:
  <path>: <tilth outline>
deps:
  <path>: <tilth_deps output>
callers:
  <symbol>: [<call sites>]
precedent: <precedent.json contents>
concurrent_prs: <concurrent-prs.json contents>
impact_radius: <get_impact_radius output or null>
```

No inline source content in the pack. Agents use `cheez-read` for
follow-up source reads after reviewing the outline.

## Phase 2 — Dispatch All 8 Dim Agents (parallel; D-32)

Spawn all agents in parallel. Each agent:
- Reads `$RUN_DIR/evidence-pack.yaml` as primary evidence
- Reads `$RUN_DIR/diff.patch` for the change context
- Writes `$RUN_DIR/<dim>.json` per the per-agent return contract
  (see `skills/age/references/sidecar-schema.md`)

Agents to dispatch:
- `age-correctness`
- `age-security`
- `age-complexity`
- `age-encapsulation`
- `age-spec`
- `age-precedent`
- `age-deslop`
- `age-assertions`

Pass to each agent: `RUN_DIR`, `REF`, `SCOPE`, `COMPREHENSIVE` flag.

When an agent's dim does not apply to the diff, it emits:

```json
{"dimension": "<dim>", "scope_match": false, "observations": [], "stake": "<dim-stake>", "summary": "Dim does not apply to this diff."}
```

## Phase 3 — Synthesize (orchestrator, deterministic; no LLM)

Collect all `$RUN_DIR/<dim>.json` files.

```
observations = union(all dim.json observations)
callouts = group_by_locus(observations, window=3 lines, min_dims=2)
```

**group_by_locus**: observations from 2+ dims whose `anchor.start` line
numbers fall within 3 lines of each other become a cross-dim callout.

**Render Markdown report** → `.cheese/age/<slug>.md`:

```
# Age Report — <slug>

## Orientation
<1-2 sentence factual description of what the diff does>

Ran 8 dims. <N> had findings. <8-N> were empty (scope_match: false or no observations).

## High-Stake Dimensions
(correctness, security, encapsulation, spec — non-empty only)

## Medium-Stake Dimensions
(complexity, deslop, assertions — non-empty only)

## Advisory Dimensions
(precedent — non-empty only)

## Cross-Dimension Callouts
(loci where 2+ dims agree; omit section if empty)
```

See `skills/age/references/report-template.md` for full layout and
narrative format rules.

**Split observations into sidecar JSON files:**

`.cheese/age/<slug>.fixes.json`:
- observations with a `fix` field (hash-anchored, syntactically narrow,
  complete content)

`.cheese/age/<slug>.suggestions.json`:
- observations with `consideration` only (no `fix`)

Both match the schema in `skills/age/references/sidecar-schema.md`.

## Phase 4 — Hand-off (no auto-invoke)

Print:

```
Age report: .cheese/age/<slug>.md
Fixes:       .cheese/age/<slug>.fixes.json   (<N> entries)
Suggestions: .cheese/age/<slug>.suggestions.json   (<M> entries)

Next step:
  /cure <slug>                              — apply fixes, route suggestions, re-age
```

Do NOT auto-invoke /cure. The amplifier-pure boundary forbids it
(spec D-14-final). The report is the deliverable; the user types the
hand-off.

## Phase 5 — Cleanup

```bash
rm -rf "$RUN_DIR"
```

## Rules

- File I/O from dim agents via `cheez-read` / `cheez-search` (NFR-1).
  No host `Read` / `Grep` / `Edit`, no direct `tilth_edit`.
- Hash anchors use tilth `line:hash` strings natively (NFR-2, D-24).
- No numeric scores anywhere in user-facing output (D-5).
- Confidence rendered as `low | med | high` bucket only.
- Narrative before bucket in every observation (Greptile severity-at-end).
- No writes to production source files during review (FR-8, NFR-6).
- Dim stake is fixed per dim; do not vary at runtime.
