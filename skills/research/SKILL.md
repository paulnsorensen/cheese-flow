---
name: research
description: Multi-source research orchestrator that routes questions across Context7 library docs, Tavily web research, codebase analysis, and GitHub examples, then returns a compact synthesis with confidence scoring.
license: MIT
compatibility: Works in markdown-based coding harnesses with sub-agent support. Context7, Tavily, and GitHub lookups are optional source routes.
metadata:
  owner: cheese-flow
  category: research
allowed-tools:
  - read
  - write
  - bash
  - subagent
  - mcp
---
# Research

Use this skill when the user asks to research a technical question, compare
libraries or approaches, investigate external APIs, or gather 2+ sources before
making an implementation decision.

Do not use this skill for a single library-doc lookup, a codebase-only question,
or a simple fact that can be answered directly.

## Context Discipline

Run the orchestration inline, but keep raw evidence out of the main context:

1. Route sources once and state the committed routing decision.
2. Spawn fetchers in parallel where the harness supports it.
3. Resolve the canonical project `.cheese` root, then spawn knowledge-base
   scanner sub-agents against `<canonical-project-root>/.cheese/research`.
4. Have fetchers write findings to scratch files under `$TMPDIR`.
5. Have one synthesis sub-agent read those scratch files and return the final
   answer.
6. Write the full report to
   `<canonical-project-root>/.cheese/research/<slugified-topic>.md`.
7. Delete the scratch directory after the report is written.

The caller should see only the routing decision, fetcher status, synthesis,
and the report path.

## Arguments

The entire request body is the research question. The skill always writes a
full report; the caller does not pass an output path.

Create a run directory:

```bash
RUN_ID="$(date +%Y%m%d-%H%M%S)-<slug>"
RUN_DIR="${TMPDIR:-/tmp}/cheese-flow-research-${RUN_ID}"
mkdir -p "$RUN_DIR"
```

Use a 4-6 word kebab-case slug derived from the topic.

## Canonical `.cheese` Resolution

Research reports are durable project knowledge. Do not strand them in a
throwaway linked worktree's `.cheese/`.

Resolve the canonical project root before reading or writing research:

```bash
ACTIVE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CANONICAL_ROOT="$(
  git -C "$ACTIVE_ROOT" worktree list --porcelain 2>/dev/null \
    | awk 'BEGIN { RS=""; FS="\n" } NR == 1 { sub(/^worktree /, "", $1); print $1 }'
)"
CANONICAL_ROOT="${CANONICAL_ROOT:-$ACTIVE_ROOT}"
CHEESE_ROOT="$CANONICAL_ROOT/.cheese"
RESEARCH_DIR="$CHEESE_ROOT/research"
mkdir -p "$RESEARCH_DIR"
```

In a normal checkout, `CANONICAL_ROOT` and `ACTIVE_ROOT` are the same. In a
Conductor or Git linked worktree, `CANONICAL_ROOT` is the main worktree path.

When a user explicitly provides another output path, honor it. Otherwise all
research reports go under `$RESEARCH_DIR`.

## Persistent Report Frontmatter

Every report written to `.cheese/research/` must start with YAML frontmatter:

```yaml
---
title: "<human title>"
slug: "<kebab-case-slug>"
question: "<original user question>"
created_at: "YYYY-MM-DDTHH:mm:ssZ"
updated_at: "YYYY-MM-DDTHH:mm:ssZ"
last_validated_at: "YYYY-MM-DDTHH:mm:ssZ"
status: "active"
confidence: 0
freshness:
  status: "fresh"
  source_volatility: "low"
  half_life_days: 180
  next_review_at: "YYYY-MM-DDTHH:mm:ssZ"
  revalidation_reason: ""
relevance:
  status: "direct"
  score: 100
  matched_terms: []
tags: []
sources: []
related: []
---
```

Allowed values:

- `status`: `draft`, `active`, `superseded`, `archived`.
- `freshness.status`: `fresh`, `stale`, `needs_revalidation`,
  `unverified`.
- `freshness.source_volatility`: `low`, `medium`, `high`.
- `relevance.status`: `direct`, `partial`, `background`, `unrelated`.

When updating an existing report, preserve `created_at`, set `updated_at` and
`last_validated_at` to the current time, and append any superseded report paths
to `related`.

## Freshness and Relevance Algorithm

The knowledge-base scan is advisory, but it must judge whether prior research
can be reused.

For each candidate report:

1. Parse frontmatter. If missing, treat it as `unverified`.
2. Compute relevance:
   - `direct` (90-100): same decision, library, API, architecture, or spec.
   - `partial` (60-89): same domain but different question.
   - `background` (30-59): useful context only.
   - `unrelated` (0-29): ignore for synthesis.
3. Compute volatility:
   - `high`: model docs, vendor APIs, prices, laws, schedules, benchmarks,
     package versions, security posture, product features.
   - `medium`: framework guidance, library usage, current OSS maintenance,
     local code architecture.
   - `low`: durable architecture principles, historical explanations,
     internal decisions that have not been reversed.
4. Assign freshness half-life:
   - high: 14 days.
   - medium: 45 days.
   - low: 180 days.
5. Mark `needs_revalidation` when any is true:
   - age since `last_validated_at` exceeds half-life,
   - report has no frontmatter or no sources,
   - relevant local file refs changed since the report date,
   - cited vendor/library/model docs are likely current-sensitive,
   - confidence is below 70,
   - current routed sources contradict the prior report.

Use judgment. A stale but still relevant report can guide search queries, but it
cannot be the sole evidence for current facts.

## Phase 1: Classify

Identify:

- Primary topic
- Question type: factual lookup, how-to, comparison, pattern search, API usage
- Complexity: simple fact, focused question, comparison, or deep analysis
- Constraints: version, language, framework, performance, license, architecture

## Phase 1.5: Knowledge-Base Scan

Always inspect existing research before external fetching.

Spawn knowledge-base scanner sub-agents against `$RESEARCH_DIR`:

- If the directory is empty, write `<RUN_DIR>/knowledge-base.md` with
  `Status: unavailable` and reason `no existing research`.
- If there are 1-20 reports, spawn one scanner.
- If there are more than 20 reports, spawn up to three scanners sharded by
  filename or topic. Each scanner writes one scratch file; the synthesis agent
  reads all completed shard files.

Scanner prompt shape:

```text
You are scanning the project research knowledge base.

Question: <question>
Research dir: <RESEARCH_DIR>

Steps:
1. Read filenames and YAML frontmatter first.
2. Rank candidate reports by relevance to the question.
3. For direct or partial matches, read the body enough to extract the prior
   finding, sources, confidence, freshness status, and revalidation needs.
4. Apply the freshness and relevance algorithm from the research skill.
5. Write findings to <RUN_DIR>/knowledge-base-<shard>.md using the scratch
   schema plus a "Revalidation" section.
6. Return only: done: <RUN_DIR>/knowledge-base-<shard>.md

Do not browse the web. Do not edit reports. Do not treat stale reports as
current evidence.
```

An empty knowledge base does not cap confidence. A relevant but stale or
contradicted report should lower confidence until revalidated.

## Phase 2: Route Sources

Decide once. If a source is committed here, it must be executed in Phase 3.

```text
Is it about a specific library API, config, or migration?
  YES -> Context7, plus GitHub if real-world usage matters

Is it a factual, current, vendor, product, or "what/who/when" question?
  YES -> Tavily basic search

Is it a "how should I..." or best-practices question?
  YES -> Tavily advanced search, plus Context7 when a named library is involved

Is it about patterns in this repo?
  YES -> Codebase fetcher

Is it about how open-source projects solve something?
  YES -> GitHub fetcher, plus Tavily if written analysis would help
```

Source guide:

| Source | Best For | Notes |
| --- | --- | --- |
| Context7 | Library APIs, config, migration notes | Prefer over general web for named dependencies. |
| Tavily | Current facts, technical articles, vendor docs, best practices | Use basic for factual lookups, advanced for analysis. |
| Codebase | Local conventions, existing usage, constraints | Use repository search and reads. |
| GitHub | Real-world OSS usage patterns | Use `gh` or the harness GitHub integration. |
| Knowledge Base | Prior `.cheese/research` reports and specs | Always scan before external fetches; revalidate stale direct matches. |

Emit a compact routing block:

```text
ROUTING DECISION:
- Context7: YES (library: "<library>", query: "<focused question>")
- Tavily: YES (query: "<natural-language question>", depth: basic|advanced)
- Codebase: NO (external-only question)
- GitHub: NO (not looking for OSS usage patterns)
- Knowledge Base: YES (always scan project-root .cheese/research)
```

## Phase 3: Execute Fetchers

Hard rule: if a source was committed in Phase 2, spawn it in Phase 3. Do not
silently skip a routed source because it seems low value later.

Every fetcher must:

1. Use only its assigned source tools.
2. Write findings to `<RUN_DIR>/<source>.md`.
3. Return exactly one status line:
   - `done: <RUN_DIR>/<source>.md`
   - `unavailable: <one-line reason>`

Scratch file schema:

```markdown
# <source> - <topic>
_Confidence: <0-100>_  _Status: <ok|unavailable>_

## Direct Answer
<1-2 sentences>

## Evidence
<quotes, snippets, key facts, or code references>

## Sources
- <URLs, file refs, library IDs, repo links>
```

### Context7 Fetcher

Use Context7 for library documentation. Resolve the library first, then query
the resolved docs. Limit to 3 Context7 calls.

Prompt shape:

```text
You are fetching library documentation via Context7.
Use only Context7 MCP tools. Do not use web search.

Steps:
1. Resolve the library ID for "<library>".
2. Query docs for "<focused question>".
3. Verify the resolved library matches the question.
4. Write findings to <RUN_DIR>/context7.md using the scratch schema.
5. Return only: done: <RUN_DIR>/context7.md

If Context7 is unavailable, write a one-line unavailable note to the scratch
file and return only: unavailable: <reason>
```

### Tavily Fetcher

Use Tavily for web, facts, technical articles, product docs, and current
ecosystem context. Do not route Serper; Tavily is the web source.

Prompt shape:

```text
You are researching with Tavily.
Use only Tavily MCP tools. Do not use generic web search.

Query: "<natural-language question>"
Depth: basic for factual/current lookups, advanced for how-to or comparisons.

Steps:
1. Search with the selected depth.
2. If snippets are insufficient, extract from one promising URL.
3. Max 3 Tavily calls.
4. Write findings to <RUN_DIR>/tavily.md using the scratch schema.
5. Return only: done: <RUN_DIR>/tavily.md

Do not use high-cost deep research tools unless the user explicitly asked for
deep research.
```

### Codebase Fetcher

Use repository tools to find local precedents and constraints.

Prompt shape:

```text
You are analyzing the local codebase for patterns.
Question: <question>

Find:
- Existing usage of this dependency, pattern, or architecture
- Constraints implied by current code
- File references that matter to the decision

Write findings to <RUN_DIR>/codebase.md and return only:
done: <RUN_DIR>/codebase.md
```

### Knowledge-Base Fetcher

The knowledge-base scan runs in Phase 1.5 before source routing completes. If it
found direct or partial matches, include them as a committed Phase 3 source and
use the findings to shape external queries.

Do not use prior research as current evidence unless freshness is `fresh` or the
current run revalidates its load-bearing claims.

### GitHub Fetcher

Use GitHub for real-world open-source patterns.

Prompt shape:

```text
You are searching GitHub for real-world examples.
Use the harness GitHub integration or `gh` CLI.

Find:
- 2-3 relevant public examples
- Observable implementation patterns
- Caveats or maintenance signals

Write findings to <RUN_DIR>/github.md and return only:
done: <RUN_DIR>/github.md
```

## Phase 4: Synthesis

Spawn one synthesis sub-agent. It reads each `done` scratch file and ignores
unavailable sources for content while still counting them in confidence.

Synthesis task:

1. Build one evidence row per routed source:
   `Source | Finding | Score | Notes`.
2. Apply the mechanical confidence cap:
   - Any unavailable, failed, skipped, or not-spawned committed source caps
     overall confidence at 49.
   - Exception: an empty knowledge base with no prior reports does not cap
     confidence; it is absence of prior evidence, not a failed source.
   - 3+ agreeing sources: 85-100.
   - 2 agreeing sources: 60-84.
   - Disagreement: cap at 49 and explain why.
   - 1 completed source: inherit that source's score.
3. Return exactly:

```markdown
## Research: <Question>

### Finding
<1-3 concise paragraphs>

### Evidence by Source
| Source | Finding | Score | Notes |
| --- | --- | --- | --- |
| ... |

### Implications
<2-4 sentences about how this affects the user's task>

### Overall Confidence
**<score>** - <justification based on source agreement and completeness>
```

After the synthesis block, append a fenced `report-body` block containing a
full markdown report with YAML frontmatter, source URLs, file refs, and repo
links. The orchestration layer writes that report body verbatim to
`<canonical-project-root>/.cheese/research/<slug>.md`.

## Cleanup

After the report is written:

```bash
rm -rf "$RUN_DIR"
```

## Rules

- Do not read scratch files in the main context.
- Do not write application code or implement the researched solution.
- Do not use Serper or SerperAPI; Tavily is the web and facts source.
- Do not use high-cost Tavily deep research unless the user explicitly asks.
- Do not skip a source that was committed in the routing decision.
- If a routed source fails, surface the incomplete confidence cap instead of
  pretending the remaining evidence is complete.
