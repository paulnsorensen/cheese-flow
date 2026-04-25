# References

Long-form architectural and engineering references that ship alongside cheese-flow. Source-of-truth documents that agents and skills can cite, quote, or load on demand. Intentionally not wired into any specific skill yet.

## Sliced Bread Architecture

| Document | When to load |
|---|---|
| [sliced-bread.md](./sliced-bread.md) | **Always.** Language-agnostic rationale, growth pattern, anti-patterns, boundary decisions, dependency-direction quick-check, review checklist. Start here. |
| [sb/practice.md](./sb/practice.md) | Applied patterns: slice-local duplication tolerance, CQRS within a slice, anti-corruption layers, testing strategy per slice, and slice graduation (when to promote a slice to a workspace package, library, or service). |
| [sb/attribution.md](./sb/attribution.md) | When reviewers question the architectural choices. Predecessor lineage (VSA, Hexagonal, Screaming, Clean, Onion, DDD), what's inherited, what's deliberately dropped, terminology distinctions (especially "shared kernel" vs "common leaf"). |
| [sb/rust.md](./sb/rust.md) | When the codebase is Rust. Module privacy, the `foo.rs` + `foo/` facade convention, `pub use` re-exports, workspaces. |
| [sb/go.md](./sb/go.md) | When the codebase is Go. The `internal/` directory as compile-time enforcement, package = directory, `go.work` workspaces. |
| [sb/ts.md](./sb/ts.md) | When the codebase is TypeScript. `package.json` `"exports"` maps as the modern facade, why barrel files are now anti-pattern, project references, monorepo workspaces. |
