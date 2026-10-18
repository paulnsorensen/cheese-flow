---
status: reviewed
last_verified: 2026-10-18
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
  - python/cheese_flow/models.py
  - python/cheese_flow/install.py
  - python/cheese_flow/profiles/models.py
  - python/cheese_flow/profiles/parse.py
  - python/cheese_flow/profiles/journal.py
  - python/cheese_flow/profiles/source.py
---
# Cheese-flow domain model

This page names the domain terms of cheese-flow and points each term at its code. The agent-profile extraction shipped (PR #98 and #99). Every term now has a concrete class or function. Code pointers name symbols, not line numbers, because line numbers drift. The module layout is flat under `python/cheese_flow/`, so `python/cheese_flow/lib/harness.py` no longer exists.

**Desired state**: The user-approved harnesses, components, discovery bounds, and selected canonical repositories that installation must converge toward.
_Avoid_: observed state
_Code_: `python/cheese_flow/models.py` (`class DesiredState`)

**Install plan**: The deterministic per-run sequence of native commands, dependencies, and positive postconditions derived from desired state.
_Avoid_: compiler plan
_Code_: `python/cheese_flow/models.py` (`class InstallPlan`)

**Repository candidate**: A Git repository found under an explicit search root, canonicalized to its main repository, classified, and left unselected until the user chooses it.
_Avoid_: automatically selected repository
_Code_: `python/cheese_flow/models.py` (`class RepositoryCandidate`)

**Verified convergence**: The execution rule that skips a satisfied postcondition, runs only unmet work, and verifies again before declaring success.
_Avoid_: command idempotency
_Code_: `python/cheese_flow/install.py` (`def apply_install_plan`)

**Apply report**: The normalized machine-readable result of executing an install plan.
_Avoid_: `InstallReport`
_Code_: `python/cheese_flow/models.py` (`class ApplyReport`)

**Doctor report**: The normalized machine-readable result of checking desired state without changing cheese-managed state.
_Code_: `python/cheese_flow/models.py` (`class DoctorReport`)

**Component adapter**: The boundary that owns one component's native installation argv and positive verification checks.
_Avoid_: unified MCP proxy
_Code_: `python/cheese_flow/models.py` (`class ComponentAdapter(Protocol)`)

**Harness**: A supported coding-agent host whose native configuration receives component plugins, skills, or MCP registration.
_Avoid_: component
_Code_: `python/cheese_flow/models.py` (`HarnessName`: Claude Code, Codex, Cursor). The profile domain has wider harness literals in `python/cheese_flow/profiles/models.py` (`CompileHarnessName`, `LaunchHarnessName`, `IsolatedLaunchHarnessName`, `ProjectPermissionHarnessName`). The profile surface supports more harnesses than the v1 installer, so the two do not share a type.

**Profile source root**: The explicit caller-owned directory containing `profiles/` and declared registry/body inputs for one resolution operation.
_Avoid_: dotfiles directory, profile home
_Code_: `python/cheese_flow/profiles/source.py` (`list_profiles`), checked by `validate_explicit_source_root` in `python/cheese_flow/profiles/paths.py`.

**Resolved profile**: One validated profile after include expansion, registry lookup, precedence application, and environment substitution.
_Avoid_: manifest
_Code_: `python/cheese_flow/profiles/parse.py` (`class ResolvedProfile`)

**Compile target**: A named symbolic deployment root paired with its explicitly resolved filesystem root and supported harnesses.
_Avoid_: install target
_Code_: `python/cheese_flow/profiles/models.py` (`class CompileTarget`)

**Compile generation**: The immutable content identity of one canonical profile compilation, encoded as a lowercase SHA-256 digest and published beneath `generations/<generation>/`.
_Avoid_: build directory
_Code_: `python/cheese_flow/profiles/models.py` (`CompiledProfileManifest.generation`, checked by `_generation_is_lowercase_sha256`)

**Compiled profile manifest**: The schema-versioned publication binding a resolved profile identity, compile targets, drift, destinations, fragment hashes, and one compile generation.
_Avoid_: profile manifest
_Code_: `python/cheese_flow/profiles/models.py` (`class CompiledProfileManifest`)

**Profile apply state**: The schema-versioned set of live files currently owned by profile apply.
_Avoid_: install state
_Code_: `python/cheese_flow/profiles/models.py` (`class ProfileApplyState`)

**Profile apply report**: The exact copied and deleted paths plus the profile apply state committed by one operation.
_Avoid_: apply report
_Code_: `python/cheese_flow/profiles/models.py` (`class ProfileApplyReport`)

**Profile apply journal**: The private persisted recovery record that identifies the immutable manifest transaction, previous and desired ownership, and its durable phase.
_Avoid_: rollback log
_Code_: `python/cheese_flow/profiles/journal.py` (`class ProfileApplyJournal`, private to the `profiles` package)

**Launch spec**: A fully validated executable, argv, and secret-safe immutable environment snapshot derived from one resolved profile without applying it.
_Avoid_: launch command
_Code_: `python/cheese_flow/profiles/models.py` (`class LaunchSpec`)

**Project permissions request**: An explicit project root, local-mode choice, and closed Claude/Codex harness selection for rendering the fixed repository permission fragment.
_Avoid_: perms command
_Code_: `python/cheese_flow/profiles/models.py` (`class ProjectPermissionsRequest`)

**Project permissions report**: The exact project configuration paths written and harnesses deliberately skipped by project-permission rendering.
_Avoid_: permissions result
_Code_: `python/cheese_flow/profiles/models.py` (`class ProjectPermissionsReport`)
