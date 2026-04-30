---
name: skill-improver
description: Agent and skill code auditor. Runs five orthogonal LLM dimensions (activation, tool-scoping, context, prompt-quality, output-format) and emits evidence-backed observations with optional hash-anchored fixes.
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

# skill-improver — Agent and Skill Auditor

Amplify the agent/skill author's attention. Surface evidence, unknowns, and
activation defects. Do not render verdicts.

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

## Always-Fire Rationale

All 5 dims fire on every invocation. Gating by heuristics risks silent misses.
Each agent self-noops with `scope_match: false` + empty observations when its
rubric does not apply. Empty dims are tallied; only non-empty dims render as
report sections.

## Arguments

```
/skill-improver <agent-path | skill-path>
```

- `path` — path to the target agent (e.g., `agents/foo.md.eta`)
  or skill (e.g., `skills/foo/SKILL.md`).
- With no path, ask the user (mirrors `/mold`'s "if no path, ask" rule).

## Phase 0 — Classify (no LLM)

Parse argv: extract target path. Validate file exists. Classify as agent or skill.

```bash
TARGET="$1"
if [ ! -f "$TARGET" ]; then
  echo "ERROR: File not found: $TARGET" >&2
  exit 1
fi
SLUG="$(basename "$TARGET" | tr '/:.-' '----' | head -c 32)"
RUN_DIR="${TMPDIR:-/tmp}/cheese-flow-skill-improver-$(date +%Y%m%d-%H%M%S)-${SLUG}"
mkdir -p "$RUN_DIR"
```

## Phase 1 — Pre-fetch Evidence (parallel)

Run all fetches in parallel. Merge into `$RUN_DIR/evidence-pack.yaml`.

**Parallel tasks:**

- `cheez-read $TARGET` → full file content
- `cheez-search <symbols-in-target>` → usages and definitions
- Parse frontmatter with `parseFrontmatter()` → extract metadata

**Merge into evidence pack:**

```yaml
# $RUN_DIR/evidence-pack.yaml
target: <TARGET>
target_type: agent|skill
source: <full file content>
frontmatter: <parsed frontmatter object>
outline: <cheez-read outline mode>
usages: <cheez-search results>
```

No inline source in outline mode; agents use `cheez-read` for follow-up reads.

## Phase 2 — Dispatch All 5 Dim Agents (parallel)

Spawn all agents in parallel. Each agent:
- Reads `$RUN_DIR/evidence-pack.yaml` as primary evidence
- Reads `references/<dim>/protocol.md` for the per-dim rubric
- Calls `cheez-read $TARGET` directly for follow-up source reads
- Writes `$RUN_DIR/<dim>.json` per the per-agent return contract

Agents to dispatch:
- `skill-improver-activation`
- `skill-improver-tool-scoping`
- `skill-improver-context`
- `skill-improver-prompt-quality`
- `skill-improver-output-format`

Pass to each agent: `RUN_DIR`, `TARGET`, `TARGET_TYPE`.

When a dim does not apply, it emits:

```json
{"dimension": "<dim>", "scope_match": false, "observations": [], "stake": "<dim-stake>", "summary": "Dim does not apply."}
```

## Phase 3 — Synthesize (orchestrator, deterministic; no LLM)

Collect all `$RUN_DIR/<dim>.json` files.

**Render Markdown report** → `.cheese/skill-improver/<slug>.md`:

```
# Skill-Improver Report — <slug>

## Orientation
<1-2 sentence factual description of the target file>

Ran 5 dims. <N> had findings. <5-N> were empty.

## High-Stake Dimensions
(activation, tool-scoping — non-empty only)

## Medium-Stake Dimensions
(context, prompt-quality, output-format — non-empty only)

## Cross-Dimension Callouts
(loci where 2+ dims agree; omit if empty)
```

**Split observations into sidecar JSON files:**

`.cheese/skill-improver/<slug>.fixes.json`:
- observations with a `fix` field (hash-anchored, syntactically complete)

`.cheese/skill-improver/<slug>.suggestions.json`:
- observations with `consideration` only (no `fix`)

Both match the schema in `skills/age/references/sidecar-schema.md` (shared with
/age and /cleanup for cross-flow reuse via cleanup-wolf).

## Phase 4 — Hand-off (no auto-invoke)

Print:

```
Skill-improver report: .cheese/skill-improver/<slug>.md
Fixes:                 .cheese/skill-improver/<slug>.fixes.json   (<N> entries)
Suggestions:           .cheese/skill-improver/<slug>.suggestions.json   (<M> entries)

Next steps:
  /cleanup <slug>                           — apply mechanical fixes
  /fromage cook --suggestions <slug>        — act on judgment guidance
```

Do NOT auto-invoke either skill. The amplifier-pure boundary forbids it
(spec FR-8, SI-3 inheriting `/age` D-14-final). The report is the
deliverable; action is the user's call.

## Phase 5 — Cleanup

```bash
rm -rf "$RUN_DIR"
```

## Rules

- File I/O from dim agents via `cheez-read` / `cheez-search` (NFR-1).
  No host `Read` / `Grep` / `Edit`, no direct `tilth_edit`.
- Hash anchors use tilth `line:hash` strings natively (NFR-2).
- No numeric scores in user-facing output.
- Confidence rendered as `low | med | high` bucket only.
- Narrative before bucket in every observation.
- No writes to production source files during review. `/cleanup` is the
  only path that writes; `/skill-improver` never invokes it (FR-8).
- Dim stake is fixed per dim; do not vary at runtime.
