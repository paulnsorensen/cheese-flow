# DAG_HEALTH

Design-quality scoreboard for the cheese-flow agent + DAG ecosystem. Every
row scored 0–100. The ralph stops when every row is >= 90.

Last updated: 2026-04-26, iteration 3.

## Flows (from Quintessential Agentic Flows for Cheese-Flow.md)

| Flow | Score | Notes |
|---|---|---|
| 1. Spec-First (Cook → Cut → Press → Age) | 35 | Stage agents exist but no top-level command anchors this flow; spec→cook hand-off is undocumented; entry skips Culture but no agent acknowledges that. |
| 2. Exploration (Culture → Cook iterative → Cut → Press → Age) | 25 | Culture↔Cook loop semantics undefined; no gate between exploration and commit; iteration cap unspecified. |
| 3. Debug (Culture → Cook → Press → Age) | 60 | `/debug` command added with explicit Cut-skip, stage permission table, three-loop fix cap, and Culture read-only invariant. Tool-layer enforcement and dispatch wiring still deferred. |
| 4. PR-Finish (Culture → Cut → Press → Age) | 60 | `/pr-finish` command added: explicit Cook-skip rationale, per-stage permission table, AskUserQuestion-gated approval between Cut and Press, three-loop Press→Age fix cap, and divergent-PR redirect to `/mold`. Stage dispatch wiring still deferred. |
| 5. Review (Culture → Age → loop) | 55 | /age command exists with the six-dimension contract; missing the explicit Culture-pre-pass and the Age→Press fix-loop semantics. |
| 6. Incremental (Cook → Cut → Press → Age × N) | 20 | No incremental command. Loop boundary, per-iteration Culture minimization, and stop condition all unspecified. |
| 7. Learn (Culture only) | 60 | /culture command documents the no-write invariant and the exit criterion; enforcement is still prompt-only and the agent metadata does not declare read-only. |

## Agents (agents/*.md.eta)

| Agent | Score | Notes |
|---|---|---|
| culture | 65 | Output contract is structured and tight; missing explicit read-only permission posture, missing flow-entry guidance for Debug vs Learn vs Exploration. |
| cook | 60 | Workflow + plan-step table is solid; missing confidence scoring, missing structured summary file (orchestrator gets full body), Bash use is unconstrained. |
| cut | 55 | Pipeline-vs-standalone duality is documented but description still says "adversarial" instead of "TDD scaffolding"; overlap with press not adjudicated. |
| press | 55 | Confidence scoring + summary-file pattern is good; charter overlaps with cut; "guilty-until-proven" tone clear. |
| age-safety | 75 | Charter, classify→evidence→score protocol, and disjoint-with-siblings note all present; minor: no explicit Sliced-Bread cross-link for boundary bugs. |
| age-arch | 75 | Strong measurement protocol with cheez-search/tilth grounding; nesting-depth ladder is concrete; Sliced Bread coverage explicit. |
| age-encap | 75 | Sliced Bread rules embedded; cheez-search "callers" + tilth_deps grounding; classification table covers the 5 leak types. |
| age-yagni | 70 | Justification check protocol is concrete; AI_NOISE deletion fix-it-yourself rule is good; spec-cross-reference covered. |
| age-history | 80 | Modifier-only contract is tight; one-call git-file-risk discipline; cap at +15/-5 prevents stacking. |
| age-spec | 70 | Spec-first protocol with cheez-search verification; missing "no spec found" fast-exit emphasis in summary; classification table present. |

## Cross-cutting principles

| Principle | Score | Notes |
|---|---|---|
| Permission model per stage | 30 | Permission posture (Culture read-only, Press full r/w, Age annotate-only) is not enforced via tools/disallowedTools; only prompt-level guidance. |
| Confidence scoring (>= 50 to surface) | 70 | Applied uniformly across the six age-* agents and press; cook + cut + culture do not score at all. |
| Compaction seams (sub-agents return summaries, not narrative) | 55 | culture and press emit structured summaries to $TMPDIR + short returns; cook still returns full body; age-* return short tables but body lengths drift. |
| Skill-over-tool delegation | 70 | Agents prefer cheez-* skills over raw Read/Grep; basic-agent still uses raw `read/write/bash`; no skill-or-tool routing helper is shared. |
| Terse output discipline | 60 | Output formats are explicit but agent prompt bodies still carry redundant restatements (e.g. "What You Don't Do" duplicates description). |
| Stop conditions per phase | 60 | Most agents declare a "wrap-up signal" tool-call cap; culture, age-history, and basic-agent do not. |
| Cross-harness portability | 65 | Tool names + skills are in the canonical Claude vocabulary; Claude-only fields (disallowedTools, permissionMode) are tolerated by the compiler; no inline notes in eta about Codex/Copilot/Cursor approximations. |
| Sliced Bread organization | 50 | skills/ has flat one-folder-per-skill layout; no `index`/crust convention surfaced for skills with helper files; no documented growth pattern. |
| Deterministic Python tooling | 25 | python/tools/ directory does not exist; only one external helper referenced (`git-file-risk`) with no source-of-truth or test in this repo. |

## Iteration log

- Iteration 1: bootstrap — initial scoreboard with honest low-biased scores.
- Iteration 2: add `commands/debug.md` (Flow 3 entry point) — Culture→Cook→Press→Age with explicit Cut-skip, per-stage permission contract, evaluator-optimizer fix loop, and stop-condition cap.
- Iteration 3: add `commands/pr-finish.md` (Flow 4 entry point) — Culture→Cut→Press→Age with explicit Cook-skip rationale, AskUserQuestion-gated approval between Cut and Press, divergent-PR redirect to `/mold`, and three-loop Press→Age fix cap.
