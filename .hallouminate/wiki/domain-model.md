---
status: reviewed
last_verified: 2026-08-30
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
  - python/cheese_flow/models.py
  - python/cheese_flow/install.py
  - python/cheese_flow/profiles/models.py
  - python/cheese_flow/profiles/journal.py
  - python/cheese_flow/profiles/source.py
---
# Cheese-flow domain model

All entities below were "NEW ENTITY" placeholders when this page was first written
(2026-08-07, before the agent-profile extraction ADRs landed). The extraction shipped
(PR #98/#99) and every entity now has a concrete class or function; `_Code_` lines were
refreshed against the current tree on 2026-08-30. `python/cheese_flow/lib/harness.py` no
longer exists — the module layout flattened per `AGENTS.md`'s "flat modules under
`python/cheese_flow/`" — so the `Harness` pointer below moved to its actual home.

**Desired state**: The user-approved harnesses, components, discovery bounds, and selected canonical repositories that installation must converge toward.
_Avoid_: observed state
_Code_: `python/cheese_flow/models.py:241` (`class DesiredState`)

**Install plan**: The deterministic per-run sequence of native commands, dependencies, and positive postconditions derived from desired state.
_Avoid_: compiler plan
_Code_: `python/cheese_flow/models.py:394` (`class InstallPlan`)

**Repository candidate**: A Git repository found under an explicit search root, canonicalized to its main repository, classified, and left unselected until the user chooses it.
_Avoid_: automatically selected repository
_Code_: `python/cheese_flow/models.py:268` (`class RepositoryCandidate`)

**Verified convergence**: The execution rule that skips a satisfied postcondition, runs only unmet work, and verifies again before declaring success.
_Avoid_: command idempotency
_Code_: `python/cheese_flow/install.py:65` (`def apply_install_plan`)

**Apply report**: The normalized machine-readable result of executing an install plan.
_Avoid_: `InstallReport`
_Code_: `python/cheese_flow/models.py:451` (`class ApplyReport`)

**Doctor report**: The normalized machine-readable result of checking desired state without changing cheese-managed state.
_Code_: `python/cheese_flow/models.py:455` (`class DoctorReport`)

**Component adapter**: The boundary that owns one component's native installation argv and positive verification checks.
_Avoid_: unified MCP proxy
_Code_: `python/cheese_flow/models.py:477` (`class ComponentAdapter(Protocol)`)

**Harness**: A supported coding-agent host whose native configuration receives component plugins, skills, or MCP registration.
_Avoid_: component
_Code_: `python/cheese_flow/models.py:27` (`HarnessName = Literal["claude-code", "codex", "cursor"]`); the profile domain has its own, wider harness-name literals in `python/cheese_flow/profiles/models.py:26-29` (`CompileHarnessName`, `LaunchHarnessName`, `IsolatedLaunchHarnessName`, `ProjectPermissionHarnessName`) — the two do not share a type because the profile surface (Claude/Codex/Copilot/Crush/Cursor/OpenCode) supports more harnesses than the v1 installer (Claude Code/Codex/Cursor).

**Profile source root**: The explicit caller-owned directory containing `profiles/` and declared registry/body inputs for one resolution operation.
_Avoid_: dotfiles directory, profile home
_Code_: `python/cheese_flow/profiles/source.py:32` (`list_profiles(source_root: Path)`), validated by `validate_explicit_source_root` in `python/cheese_flow/profiles/paths.py`.

**Resolved profile**: One validated profile after include expansion, registry lookup, precedence application, and environment substitution.
_Avoid_: manifest
_Code_: `python/cheese_flow/profiles/models.py:154` (`class ResolvedProfile`)

**Compile target**: A named symbolic deployment root paired with its explicitly resolved filesystem root and supported harnesses.
_Avoid_: install target
_Code_: `python/cheese_flow/profiles/models.py:99` (`class CompileTarget`)

**Compile generation**: The immutable content identity of one canonical profile compilation, encoded as a lowercase SHA-256 digest and published beneath `generations/<generation>/`.
_Avoid_: build directory
_Code_: `python/cheese_flow/profiles/models.py:169` (`CompiledProfileManifest.generation`, validated by `_generation_is_lowercase_sha256`)

**Compiled profile manifest**: The schema-versioned publication binding a resolved profile identity, compile targets, drift, destinations, fragment hashes, and one compile generation.
_Avoid_: profile manifest
_Code_: `python/cheese_flow/profiles/models.py:165` (`class CompiledProfileManifest`)

**Profile apply state**: The schema-versioned set of live files currently owned by profile apply.
_Avoid_: install state
_Code_: `python/cheese_flow/profiles/models.py:190` (`class ProfileApplyState`)

**Profile apply report**: The exact copied and deleted paths plus the profile apply state committed by one operation.
_Avoid_: apply report
_Code_: `python/cheese_flow/profiles/models.py:202` (`class ProfileApplyReport`)

**Profile apply journal**: The private persisted recovery record that identifies the immutable manifest transaction, previous and desired ownership, and its durable phase.
_Avoid_: rollback log
_Code_: `python/cheese_flow/profiles/journal.py:45` (`class ProfileApplyJournal`, private to the `profiles` package)

**Launch spec**: A fully validated executable, argv, and secret-safe immutable environment snapshot derived from one resolved profile without applying it.
_Avoid_: launch command
_Code_: `python/cheese_flow/profiles/models.py:220` (`class LaunchSpec`)

**Project permissions request**: An explicit project root, local-mode choice, and closed Claude/Codex harness selection for rendering the fixed repository permission fragment.
_Avoid_: perms command
_Code_: `python/cheese_flow/profiles/models.py:235` (`class ProjectPermissionsRequest`)

**Project permissions report**: The exact project configuration paths written and harnesses deliberately skipped by project-permission rendering.
_Avoid_: permissions result
_Code_: `python/cheese_flow/profiles/models.py:243` (`class ProjectPermissionsReport`)
