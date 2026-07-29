# V1 installer boundary

Cheese-flow v1 is a TUI installer and composition shell for independent products. It installs and configures Hallouminate and easy-cheese, offers Tilth as an unselected optional component, and delegates every component operation to that component's native CLI or harness installer.[^1]

## Product contract

- Keep the `cheese-flow` project/package name and the `cheese` command.
- Launch the interactive installer from `cheese install`; retain scriptable dry-run and doctor paths.
- Save explicit desired state for selected harnesses and components. Detection recommends choices but never becomes authority.
- Use `gh skill` behind an adapter to install easy-cheese because it carries harness, scope, pin, and update metadata.
- Register component MCP servers independently. Cheese-flow does not proxy or re-export them.
- Replace the existing compiler implementation without migration or compatibility code.

## Component choices

### Hallouminate

Hallouminate and easy-cheese are the required v1 components. Hallouminate setup delegates to its binary, harness plugin, config, and `init-repo` commands rather than reproducing their behavior.[^2]

The TUI can initialize several repositories in one run. The user supplies one or more search roots; discovery is bounded to those roots; candidates start unchecked; linked worktrees resolve to their main repository; existing configs are validation-only; and apply never passes `--force`.

### Easy-cheese

Easy-cheese remains an independently installable skills product. Cheese-flow calls `gh skill` through a narrow adapter instead of importing easy-cheese internals. The adapter contains the risk from GitHub's preview command while preserving explicit harness, scope, and version intent.[^3]

### Tilth

Tilth is optional in v1 and unselected by default. The TUI may recommend it, but the saved manifest must record the user's explicit choice. When selected, cheese-flow delegates installation and MCP registration to Tilth's own CLI.

### Milknado

Milknado is post-v1 because its runtime is not ready for this installer contract. V1 removes the existing Milknado dependency, commands, demo, and cheese-flow MCP path rather than retaining unused integration code.[^4]

## Multi-repository safety model

1. Never scan the whole home directory automatically.
2. Accept user-selected roots and show the effective depth before discovery.
3. Canonicalize and deduplicate repository roots, including linked worktrees.
4. Classify every candidate as ready, configured, unwritable, worktree-to-main, or name collision.
5. Leave every discovered repository unchecked.
6. Show exact paths and planned commands before mutation.
7. Initialize each selected repository independently and continue after unrelated failures.
8. Verify each result through Hallouminate's positive checks.

## Deferred roadmap

After v1:

- Move or extract `agent-profile` into cheese-flow when agent compilation resumes.
- Decide which portable agent definitions move from personal dotfiles into the product.
- Add Milknado only after its runtime hardening is complete.
- Rebuild the cross-project roadmap from the approved v1 spec.

The unified-MCP and fused-platform directions are superseded. Their roadmap pages are retained as deprecated history until the post-spec roadmap rebuild.[^5]

## Approved specification

The v1 implementation contract was approved on 2026-07-29 and lives in the durable project corpus.[^6] It closes the TUI sequence, unversioned desired-state schema, headless JSON contract, adapter matrix, verified-convergence failure policy, interruption behavior, and repository drift checks.

The rationale is split into three records:

- [Composition installer boundary](../adr/cheese-ecosystem-composition-001.md)
- [Desired-state interaction contract](../adr/cheese-ecosystem-composition-002.md)
- [Verified convergence and repository isolation](../adr/cheese-ecosystem-composition-003.md)

[^6]: `/home/paul/.local/share/cheese/paulnsorensen-cheese-flow/specs/cheese-ecosystem-composition.md`.

[^1]: .cheese/research/cheese-flow-v1-installer/cheese-flow-v1-installer.md:1-175
[^2]: /home/paul/Dev/hallouminate/README.md:38-113; /home/paul/Dev/hallouminate/crates/hallouminate/src/cli/init_repo.rs:1-73
[^3]: /home/paul/Dev/easy-cheese/README.md:149-232; https://cli.github.com/manual/gh_skill_install
[^4]: pyproject.toml:7-15,31-32; python/cheese_flow/cli.py:148-214
[^5]: /home/paul/Dev/cheez-wiki/.hallouminate/wiki/roadmap/unify-the-mcp-surface.md; /home/paul/Dev/cheez-wiki/.hallouminate/wiki/roadmap/cheese-flow-megazord.md
