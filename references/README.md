# References

Long-form architectural and engineering references that ship alongside cheese-flow. Source-of-truth documents that agents and skills can cite, quote, or load on demand. Intentionally not wired into any specific skill yet.

## tilth MCP (Code Intelligence)

| Document | When to load |
|---|---|
| [tilth/tilth-mcp.md](./tilth/tilth-mcp.md) | **Always when using tilth tools.** Complete reference for tilth_search, tilth_read, tilth_files, tilth_deps, and tilth_edit. Hash anchor format, session deduplication, tree-sitter languages. |

## Runtime Artifact Directories

| Document | When to load |
|---|---|
| [canonical-cheese.md](./canonical-cheese.md) | When a skill writes durable research, specs, or issues under `.cheese/`, especially from a linked Git worktree or Conductor workspace. |

## Sliced Bread Architecture

| Document | When to load |
|---|---|
| [sliced-bread.md](./sliced-bread.md) | **Always.** Language-agnostic rationale, growth pattern, anti-patterns, boundary decisions, dependency-direction quick-check, review checklist. Start here. |
| [sb/practice.md](./sb/practice.md) | When the task is a *judgement call*, not a build. Load if the prompt involves: extracting or keeping near-duplicate models across slices, deciding on read/write asymmetry (CQRS), integrating with an external API or legacy system (anti-corruption layer), choosing a per-slice testing approach, or graduating a slice to a workspace package, library, or service. Skip for routine feature work inside an existing slice — `sliced-bread.md` is enough. |
| [sb/attribution.md](./sb/attribution.md) | When reviewers question the architectural choices. Predecessor lineage (VSA, Hexagonal, Screaming, Clean, Onion, DDD), what's inherited, what's deliberately dropped, terminology distinctions (especially "shared kernel" vs "common leaf"). |
| [sb/rust.md](./sb/rust.md) | When the codebase is Rust. Module privacy, the `foo.rs` + `foo/` facade convention, `pub use` re-exports, workspaces. |
| [sb/go.md](./sb/go.md) | When the codebase is Go. The `internal/` directory as compile-time enforcement, package = directory, `go.work` workspaces. |
| [sb/ts.md](./sb/ts.md) | When the codebase is TypeScript. `package.json` `"exports"` maps as the modern facade, why barrel files are now anti-pattern, project references, monorepo workspaces. |
