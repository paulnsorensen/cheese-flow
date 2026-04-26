# Iteration 9 — Permission Contracts for Read-Only Review Agents

## Problem

Scoreboard row "Permission model per stage" was at 30. The gap:

> Permission posture (Culture read-only, Press full r/w, Age annotate-only) is
> not enforced via tools/disallowedTools; only prompt-level guidance.

Two structural issues compounded this:

1. **Source disallowedTools were too lax.** age-safety / age-arch / age-encap /
   age-spec only listed `Edit, NotebookEdit`, leaving `Write` open. Their bodies
   said "Read-only — never modify files" in prose, but `Write` was never on the
   disallow list, so a model under any harness that does honor source
   `disallowedTools` (Claude Code) could still emit Write calls.
2. **No uniform prompt-level contract.** Cross-harness portability is a hard
   requirement (Codex, Copilot CLI, and Cursor don't propagate Claude's
   `disallowedTools` field). The fallback enforcement is the prompt body
   itself, but each agent expressed its read-only invariant inconsistently
   ("never modify files", "you don't fix bugs", etc.) and none enumerated the
   *positive* allowed actions, making the contract ambiguous.

## Change applied this iteration

1. **Tightened source frontmatter** for the four read-only Age dimensions that
   produce summary-only returns (no `$TMPDIR` write):
   - `age-safety.md.eta`
   - `age-arch.md.eta`
   - `age-encap.md.eta`
   - `age-spec.md.eta`

   Each now disallows `Edit, Write, NotebookEdit`. Pre-existing exemplars:
   - `age-history.md.eta` already disallowed Edit + Write + NotebookEdit + more
     (its strictest-of-the-fleet posture was the model).
   - `age-yagni.md.eta` intentionally retains Edit/Write privileges because it
     is the lone Age dimension permitted to fix dead-code findings under the
     5-line ceiling.

2. **Added a uniform `## Permission Contract` block** at the top of the body
   (right under the role line, above the existing `## Charter`) for every
   read-only review agent:
   - `culture.md.eta` — variant: `$TMPDIR` write whitelisted for the Culture
     Report.
   - `age-safety.md.eta` — strict read-only.
   - `age-arch.md.eta` — strict read-only.
   - `age-encap.md.eta` — strict read-only.
   - `age-spec.md.eta` — strict read-only.
   - `age-history.md.eta` — strict read-only with the helper-script carve-out.
   - `age-yagni.md.eta` — annotate-with-fix-it-yourself variant; trivial
     deletions only (< 5 lines, category in {DEAD_CODE, AI_NOISE}, score >= 50).

   Each block:
   - Restates the per-stage role in one sentence ("Press is the only writer in
     Flow 5; Age sub-agents annotate").
   - Lists allowed actions (read code, read specs, read-only Bash, etc.).
   - Lists disallowed actions explicitly with `**NO**` markers.
   - Adds a cross-harness note explaining what Claude Code enforces
     structurally vs what the prompt contract carries on Codex / Copilot CLI /
     Cursor.

## Cross-harness portability impact

- **Claude Code**: tighter `disallowedTools` arrays will, once the compiler
  propagates them into output frontmatter, structurally block Write calls from
  the four newly-tightened Age agents. Source-of-truth declaration is
  forward-compatible.
- **Codex / Copilot CLI / Cursor**: no per-agent allowlist surface to honor
  `disallowedTools`. The prompt-level Permission Contract is now the explicit
  fallback — every agent body documents this in the cross-harness note.

No portability regression. The `disallowedTools` field was already in the
source schema and validated; the four edits only add `Write` to the existing
block, which the compiler already tolerates.

## Why not also tighten Bash?

Considered. Decided against in this iteration:

- Read-only review agents *might* need ad-hoc `git log` runs as a fallback
  when the deterministic helpers are unavailable.
- Disallowing Bash entirely on Cursor (no per-agent allowlist) would force
  global config changes which leak across projects.

Kept the contract prompt-level: "Run mutating Bash — NO". Future iteration
can introduce a `Bash(git:*)` allowlist pattern at the harness adapter level
once the compiler propagates `disallowedTools` and the tooling lands.

## Score change

`Permission model per stage`: 30 → 60.

- +20 for the source-frontmatter tightening (four agents now declare strict
  read-only intent in the disallowedTools block).
- +10 for the uniform prompt-level contract spanning all seven read-only
  review agents.

Remaining gap to 90:

- Compiler does not yet propagate `disallowedTools` / `permissionMode` into
  the rendered harness frontmatter for any harness — adding `Write` to the
  source list is forward-compatible but currently a no-op at runtime.
  Resolving this requires a change in `src/`, which is out of scope for this
  ralph (tracked as a `blocked-on-src` note for the next pass).
- Cook / Cut / Press still lack their writer-side Permission Contracts (they
  declare what they CAN write, but not the production-vs-test boundary as a
  per-stage table). Next iteration candidate.
- Stage table in commands/*.md (Flow contracts) and per-agent contracts are
  not cross-linked yet; a sibling iteration can add that link.
