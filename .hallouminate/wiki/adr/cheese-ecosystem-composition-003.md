---
status: reviewed
last_verified: 2026-07-29
confidence: high
sources:
  - .hallouminate/wiki/architecture/v1-installer-boundary.md
---
# Installation uses verified convergence and isolated repository failure

Idempotency means that declared positive postconditions converge, not that every native command can be repeated safely. Apply checks before mutation, runs only unmet work, verifies again, and returns nonzero until every declared postcondition passes.[^1]

## Context

Hallouminate initialization protects existing configuration and must not receive `--force`. Independent package managers and harness files cannot participate in one transaction. Repository discovery also creates a time gap between Preview and mutation.[^2]

## Decision

- Build one deterministic plan with explicit dependencies and exact argv.
- Resolve npm versions once per run and use those versions for Preview and Apply without persisting pins.
- Skip a step only when native list or config validation confirms the expected component, command, and scope.
- After any command exit, verify the positive postcondition instead of trusting the exit code alone.
- Block failed dependents, continue unrelated components and repositories, and do not roll back successful work.
- Recanonicalize and reclassify each repository immediately before mutation. Drift blocks only that repository.
- Forward interruption signals to the active child, stop scheduling, postcheck, and report interruption.

## Alternatives

- Trusting command exit codes misses partial native configuration failures.
- Re-running every command is unsafe for create-only operations.
- Aborting the full run on one repository discards safe progress elsewhere.
- Cross-component rollback cannot restore package-manager and harness state reliably.

## Consequences

Reruns repair partial work and report precise remaining failures. Adapters must maintain strict positive checks. Apply reports need blocked, skipped, failed, successful, and interrupted states with redacted diagnostics.

## References

[^1]: `.cheese/research/cheese-flow-v1-installer/cheese-flow-v1-installer.md:125-149`.
[^2]: `.hallouminate/wiki/architecture/v1-installer-boundary.md:34-54`; `/home/paul/Dev/hallouminate/crates/hallouminate/src/cli/init_repo.rs:1-73`.
