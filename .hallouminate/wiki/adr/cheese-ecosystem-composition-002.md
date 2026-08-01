---
status: reviewed
last_verified: 2026-07-29
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
---
# Desired state drives interactive and headless installation

One validated TOML manifest is the authority for both the linear wizard and headless automation. Detection recommends choices but never replaces explicit desired state.[^1]

## Context

The installer must serve a first-time interactive setup and cloud environments that cannot answer prompts. The user also needs repeat runs to reconcile the same choices. Observed versions, capabilities, and execution results change independently and do not belong in desired state.[^2]

## Decision

- Store harnesses, components, discovery roots, one global depth, and selected canonical repository paths at `$XDG_CONFIG_HOME/cheese/config.toml` by default.
- Launch a linear wizard without `--config`. Existing state prefills every screen; v1 does not jump directly to Preview.
- Treat a complete `--config PATH` as headless authority. Reject incomplete state before metadata lookup or mutation.
- Write interactive state atomically immediately before Apply. Cancel and dry-run do not write managed state.
- Emit one final JSON document on stdout for headless install, dry-run, and doctor. Send progress and diagnostics to stderr.
- Keep resolved versions and observed results outside the manifest.

## Alternatives

- Detection-only state makes reruns dependent on ambient machine changes.
- A hybrid wizard adds navigation modes before the linear workflow is proven.
- Mixing progress text and JSON on stdout makes automation parse an unstable stream.
- Persistent pins add manifest lifecycle policy that v1 does not need.

## Consequences

Interactive and cloud use share validation, planning, and reporting. The manifest remains small and reviewable. Summary-first reruns and persistent version pins remain outside v1.

## References

[^1]: `.cheese/notes/cheese-ecosystem-composition.md:31-35`.
[^2]: `.cheese/research/cheese-flow-v1-installer/cheese-flow-v1-installer.md:83-123`.
