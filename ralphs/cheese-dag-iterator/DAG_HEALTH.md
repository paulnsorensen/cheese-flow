# DAG_HEALTH

Design-quality scoreboard for the cheese-flow agent + DAG ecosystem. Every
row scored 0–100. The ralph stops when every row is >= 90.

Last updated: 2026-04-26, iteration 8.

## Flows (from Quintessential Agentic Flows for Cheese-Flow.md)

| Flow | Score | Notes |
|---|---|---|
| 1. Spec-First (Cook → Cut → Press → Age) | 60 | `/fromage` command added: spec-validation gate (Approach + Quality gates required) before Cook starts, Culture folded into Cook's light pre-pass with explicit no-full-repo-scan rule, parallel-atoms classifier that redirects to `/fromagerie` (>= 4 non-overlapping units) and the linear-backlog redirect to `/incremental`, three-loop Press → Age cap, and spec-invalidation halt path that recommends `/mold` when Age challenges the spec itself. Stage dispatch wiring still deferred. |
| 2. Exploration (Culture → Cook iterative → Cut → Press → Age) | 60 | `/explore` command added: Culture↔Cook iterative loop with three-cycle cap (the cost-control gate); AskUserQuestion-gated approach lock as the hard commit boundary with three-choice menu (lock/loop/abort); per-cycle no-production-write invariant on Culture and Cook; mandatory ≥2-alternatives + "Do nothing" rule on Cook; approach-invalidation halt when Age challenges the locked approach itself; explicit redirects to `/culture`, `/mold`, `/fromage`, `/debug`. Stage dispatch wiring still deferred. |
| 3. Debug (Culture → Cook → Press → Age) | 60 | `/debug` command added with explicit Cut-skip, stage permission table, three-loop fix cap, and Culture read-only invariant. Tool-layer enforcement and dispatch wiring still deferred. |
| 4. PR-Finish (Culture → Cut → Press → Age) | 60 | `/pr-finish` command added: explicit Cook-skip rationale, per-stage permission table, AskUserQuestion-gated approval between Cut and Press, three-loop Press→Age fix cap, and divergent-PR redirect to `/mold`. Stage dispatch wiring still deferred. |
| 5. Review (Culture → Age → loop) | 65 | `/age` command rewritten as Flow 5 entry point: explicit Culture pre-pass with structured brief at `$TMPDIR/age-<slug>-context.md`, per-stage permission table (Culture+Age read-only-on-production, Press the only writer), `AskUserQuestion`-gated Press fix loop scoped to cited files only, three-loop convergence cap, `--no-fix` flag for embedded use inside other flows, spec-invalidation halt path that recommends `/mold` or `/explore`, and dual-role framing (standalone Flow 5 + reusable review primitive). Stage dispatch wiring still deferred. |
| 6. Incremental (Cook → Cut → Press → Age × N) | 60 | `/incremental` command added: per-task Cook→Cut→Press→Age contract, Culture-folded-into-Cook for minimal per-task grounding, JSON state file with resume semantics, three-loop Press→Age cap per task, explicit `/fromagerie` redirect for parallel-shaped backlogs, and per-task scope constraints in the stage table. Stage dispatch wiring still deferred. |
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
| age-history | 85 | Modifier-only contract is tight; one-call helper invocation now points at the real `python/tools/git_file_risk.py` (stdlib-only, plain `python3`) with a fall-through to a `git-file-risk` PATH shim; cross-harness portability note added. |
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
| Deterministic Python tooling | 80 | `python/tools/` bootstrapped with `git_file_risk.py` (stdlib-only, batch JSON output) plus 21 pytest cases in `tests/python/tools/test_git_file_risk.py` covering `humanize_staleness`, the three git probes, the aggregate `risk_for`, and CLI behaviour. The age-history agent is wired to call it in the same iteration — no orphan tool. Future tools (eta-frontmatter validator, harness translation matrix) still pending. |

## Iteration log

- Iteration 1: bootstrap — initial scoreboard with honest low-biased scores.
- Iteration 2: add `commands/debug.md` (Flow 3 entry point) — Culture→Cook→Press→Age with explicit Cut-skip, per-stage permission contract, evaluator-optimizer fix loop, and stop-condition cap.
- Iteration 3: add `commands/pr-finish.md` (Flow 4 entry point) — Culture→Cut→Press→Age with explicit Cook-skip rationale, AskUserQuestion-gated approval between Cut and Press, divergent-PR redirect to `/mold`, and three-loop Press→Age fix cap.
- Iteration 4: add `commands/incremental.md` (Flow 6 entry point) — per-task Cook→Cut→Press→Age × N with Culture folded into Cook for minimal per-task grounding, JSON state file with resume semantics, three-loop Press→Age cap per task, parallel-shaped-backlog redirect to `/fromagerie`, and per-task scope constraints in every stage row.
- Iteration 5: add `commands/explore.md` (Flow 2 entry point) — Culture↔Cook iterative loop with three-cycle cost-control cap, AskUserQuestion-gated approach lock as the hard commit boundary (lock/loop/abort), mandatory ≥2-alternatives + "Do nothing" rule on Cook, approach-invalidation halt path when Age findings undermine the locked approach, and per-stage no-production-write invariants on Culture and Cook.
- Iteration 6: add `commands/fromage.md` (Flow 1 entry point) — Cook → Cut → Press → Age with Culture folded into Cook's light pre-pass, hard spec-validation gate (Approach + Quality gates required), parallel-atoms classifier redirecting to `/fromagerie` (>= 4 non-overlapping units) and linear-backlog redirect to `/incremental`, three-loop Press → Age cap, and spec-invalidation halt that recommends `/mold` when Age challenges the spec itself.
- Iteration 7: rewrite `commands/age.md` as Flow 5 (Review) entry point — Culture pre-pass with structured brief, per-stage permission table (Culture+Age read-only-on-production, Press the only writer), `AskUserQuestion`-gated Press fix loop scoped to Age-cited files only, three-loop convergence cap, `--no-fix` flag for embedded use inside other flows, spec-invalidation halt path recommending `/mold` or `/explore`, and dual-role framing as both standalone Flow 5 and reusable review primitive.
- Iteration 8: bootstrap `python/tools/` with `git_file_risk.py` (stdlib-only, batch JSON output) and 21 pytest cases covering staleness humanization, the three git probes, the `risk_for` aggregator, and the CLI; rewire `agents/age-history.md.eta` to invoke `python3 python/tools/git_file_risk.py …` (with the `git-file-risk` PATH shim as a fallback) and add the cross-harness portability note. Closes the orphaned-helper gap and lifts the lowest scoreboard row from 25 → 80.
