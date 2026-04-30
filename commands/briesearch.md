---
name: briesearch
description: Multi-source research orchestrator. Routes a question across Tavily, Context7 library docs, GitHub, and in-repo tools, writes findings to .cheese/research/<slug>.md, and returns a compact synthesis to the main context.
argument-hint: "<question | library | API | dependency>"
---

# /briesearch

`/briesearch` is the research orchestrator. It routes a question across
multiple information sources in parallel, writes full findings to
`.cheese/research/<slug>.md`, and returns a compact synthesis back to the
main context so it does not pollute the caller's window.

## Execution

Invoke the `research` skill with `$ARGUMENTS`. The skill owns source routing,
scratch-file handling, synthesis, confidence scoring, optional report writing,
and cleanup.

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

Each source runs in parallel where possible. Overlapping findings are
merged; conflicts are flagged in the synthesis.

## Output contract

- **Full report** written to `.cheese/research/<slug>.md`:
  - Question and scope.
  - Source-by-source findings with inline citations.
  - Conflicts, caveats, and freshness notes.
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
