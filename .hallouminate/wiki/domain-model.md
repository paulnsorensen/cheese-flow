---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
  - ../dotfiles/agent-profile/agent_profile/parse.py
  - ../dotfiles/agent-profile/agent_profile/compiled_types.py
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

**Profile source root**: The explicit caller-owned directory containing `profiles/` and declared registry/body inputs for one resolution operation.
_Avoid_: dotfiles directory, profile home
_Code_: NEW ENTITY: source-root arguments in `cheese_flow.profiles`

**Resolved profile**: One validated profile after include expansion, registry lookup, precedence application, and environment substitution.
_Avoid_: manifest
_Code_: NEW ENTITY: `ResolvedProfile`

**Compile target**: A named symbolic deployment root paired with its explicitly resolved filesystem root and supported harnesses.
_Avoid_: install target
_Code_: NEW ENTITY: `CompileTarget`

**Compile generation**: The immutable content identity of one canonical profile compilation, encoded as a lowercase SHA-256 digest and published beneath `generations/<generation>/`.
_Avoid_: build directory
_Code_: NEW ENTITY: `CompiledProfileManifest.generation`

**Compiled profile manifest**: The schema-versioned publication binding a resolved profile identity, compile targets, drift, destinations, fragment hashes, and one compile generation.
_Avoid_: profile manifest
_Code_: NEW ENTITY: `CompiledProfileManifest`

**Profile apply state**: The schema-versioned set of live files currently owned by profile apply.
_Avoid_: install state
_Code_: NEW ENTITY: `ProfileApplyState`

**Profile apply report**: The exact copied and deleted paths plus the profile apply state committed by one operation.
_Avoid_: apply report
_Code_: NEW ENTITY: `ProfileApplyReport`

**Profile apply journal**: The private persisted recovery record that identifies the immutable manifest transaction, previous and desired ownership, and its durable phase.
_Avoid_: rollback log
_Code_: NEW PRIVATE ENTITY: `ProfileApplyJournal`

**Launch spec**: A fully validated executable, argv, and secret-safe immutable environment snapshot derived from one resolved profile without applying it.
_Avoid_: launch command
_Code_: NEW ENTITY: `LaunchSpec`

**Project permissions request**: An explicit project root, local-mode choice, and closed Claude/Codex harness selection for rendering the fixed repository permission fragment.
_Avoid_: perms command
_Code_: NEW ENTITY: `ProjectPermissionsRequest`

**Project permissions report**: The exact project configuration paths written and harnesses deliberately skipped by project-permission rendering.
_Avoid_: permissions result
_Code_: NEW ENTITY: `ProjectPermissionsReport`
