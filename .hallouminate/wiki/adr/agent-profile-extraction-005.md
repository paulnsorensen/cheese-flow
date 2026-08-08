---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - ../dotfiles/bin/dots
  - ../dotfiles/zsh/claude.zsh
  - ../dotfiles/packages/packages.yaml
---
# Dotfiles cuts over to one exact cheese-flow revision

### ADR-005: Replace agent-profile in one pinned cutover  [status: accepted]
- **Context:** An overlap would create two parsers, renderers, and deployment protocols. Live package, wrapper, registry, cache, test, documentation, and `/setup-perms` consumers exist outside `agent-profile/`.[^1]
- **Decision:** After implementation merges, dotfiles installs `https://github.com/paulnsorensen/cheese-flow` at that full feature commit, migrates every live caller, regenerates `~/.cache/cheese-flow/plugins`, and removes `agent-profile/` plus `bin/ap` together. Historical wiki/ADR/issue and one-time-migration provenance remains intact.
- **Alternatives:** Compatibility aliases create two authorities; floating refs are irreproducible; literal cleanup of historical evidence destroys provenance without changing runtime behavior.
- **Consequences:** The rollout is ordered across repositories and cannot complete before the feature commit exists. Rollback changes the exact pin rather than reviving the removed engine; the orphaned old plugin cache is not deleted.

[^1]: `../dotfiles/bin/dots:447-455`; `../dotfiles/zsh/claude.zsh:149-167`; `../dotfiles/chezmoi/lib/install-external.sh:127-137`; `../dotfiles/chezmoi/.chezmoiscripts/run_onchange_after_install-agent-profile.sh.tmpl`.
