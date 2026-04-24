---
name: briesearch
description: Multi-source research orchestrator. Routes a question across web search, library docs, and in-repo tools, writes findings to <harness>/research/<slug>.md, and returns a compact synthesis to the main context.
argument-hint: "<question | library | API | dependency>"
---

# /briesearch

`/briesearch` is the research orchestrator. It routes a question across
multiple information sources in parallel, writes full findings to
`<harness>/research/<slug>.md`, and returns a compact synthesis back to the
main context so it does not pollute the caller's window. `<harness>` is the
active harness output root — `.claude` for Claude Code, `.codex` for Codex.

## Source routing

| Source | Tool | Best for |
|---|---|---|
| General web | Tavily | Broad technical content, blog posts, long-form material |
| SERP + facts | Serper | Up-to-date facts, product pages, vendor documentation |
| Library docs | Context7 | API reference, configuration, migration notes |
| In-repo context | tilth, ripgrep, LSP | How the target codebase already handles related concerns |

Each source runs in parallel where possible. Overlapping findings are
merged; conflicts are flagged in the synthesis.

## Output contract

- **Full report** written to `<harness>/research/<slug>.md`:
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

## Deferred behavior

> **Scaffold notice.** Parallel source dispatch and the
> `<harness>/research/<slug>.md` write are not yet wired. This file
> documents the routing and output contract. The current implementation
> should describe what `/briesearch` would do and stop — it does not yet
> call Tavily, Serper, Context7, or the codebase tools.

The next iteration will:

- Dispatch the four source lookups in parallel via the `Agent` tool.
- Merge findings, flag conflicts, and write the full report.
- Return only the compact synthesis to the caller's context window.
