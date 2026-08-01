---
status: reviewed
last_verified: 2026-07-29
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
---
# Cheese-flow domain model

**Desired state**: The user-approved harnesses, components, discovery bounds, and selected canonical repositories that installation must converge toward.
_Avoid_: observed state
_Code_: NEW ENTITY: `DesiredState`

**Install plan**: The deterministic per-run sequence of native commands, dependencies, and positive postconditions derived from desired state.
_Avoid_: compiler plan
_Code_: NEW ENTITY: `InstallPlan`

**Repository candidate**: A Git repository found under an explicit search root, canonicalized to its main repository, classified, and left unselected until the user chooses it.
_Avoid_: automatically selected repository
_Code_: NEW ENTITY: `RepositoryCandidate`

**Verified convergence**: The execution rule that skips a satisfied postcondition, runs only unmet work, and verifies again before declaring success.
_Avoid_: command idempotency
_Code_: NEW ENTITY: `apply_install_plan`

**Apply report**: The normalized machine-readable result of executing an install plan.
_Avoid_: `InstallReport`
_Code_: NEW ENTITY: `ApplyReport`

**Doctor report**: The normalized machine-readable result of checking desired state without changing cheese-managed state.
_Code_: NEW ENTITY: `DoctorReport`

**Component adapter**: The boundary that owns one component's native installation argv and positive verification checks.
_Avoid_: unified MCP proxy
_Code_: NEW ENTITY: `ComponentAdapters`

**Harness**: A supported coding-agent host whose native configuration receives component plugins, skills, or MCP registration.
_Avoid_: component
_Code_: `python/cheese_flow/lib/harness.py:20`
