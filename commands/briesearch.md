---
name: briesearch
description: Multi-source research orchestrator. Scans the canonical project .cheese/research knowledge base, routes a question across Tavily, Context7 library docs, GitHub, and in-repo tools, writes frontmatter-backed findings to .cheese/research/<slug>.md, and returns a compact synthesis to the main context.
argument-hint: "<question | library | API | dependency>"
---

# /briesearch

`/briesearch` is the research orchestrator. It first scans the canonical
project `.cheese/research` knowledge base, then routes a question across
multiple information sources in parallel, writes full findings to
`.cheese/research/<slug>.md`, and returns a compact synthesis back to the main
context so it does not pollute the caller's window.

## Execution

Invoke the `research` skill with `$ARGUMENTS`. The skill owns canonical
`.cheese` root resolution, knowledge-base scanning, source routing,
scratch-file handling, synthesis, confidence scoring, report frontmatter, and
cleanup.

Do not reimplement the fetcher workflow in this command. This command is the
user-facing alias and contract for research; `skills/research/SKILL.md` is the
implementation source of truth.

## Source routing

| Source | Tool | Best for |
|---|---|---|
| Web + facts | Tavily | Broad technical content, recency, product pages, vendor documentation |
| Library docs | Context7 | API reference, configuration, migration notes |
| In-repo context | tilth, ripgrep, LSP | How the target codebase already handles related concerns |
| Open-source examples | GitHub | How public projects solve similar problems |
| Prior project research | `.cheese/research` scanner sub-agents | Existing findings, freshness, supersession, and revalidation targets |

Each source runs in parallel where possible. Overlapping findings are
merged; conflicts are flagged in the synthesis.

## Output contract

- **Full report** written to `.cheese/research/<slug>.md`:
  - YAML frontmatter with `created_at`, `updated_at`,
    `last_validated_at`, `confidence`, freshness, relevance, tags,
    sources, and related reports.
  - Question and scope.
  - Source-by-source findings with inline citations.
  - Conflicts, caveats, freshness notes, and revalidation status.
  - Recommended next step (e.g. "adopt library X", "build in-house",
    "invoke `/mold` to spec this out").
- **Synthesis** returned to the caller:
  - A compact summary (<1K tokens) of the key findings.
  - The single recommended next step.
  - A pointer to the full report path.

## Use cases

- Choosing between libraries that solve the same problem.
- Understanding an unfamiliar API before integrating it.
- Investigating a dependency (maturity, license, maintenance activity).
- Pulling external context before `/mold` or `/cheese` so the spec is
  informed, not speculative.
