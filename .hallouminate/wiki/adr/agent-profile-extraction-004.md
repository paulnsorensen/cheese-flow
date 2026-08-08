---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - ../dotfiles/agent-profile/agent_profile/overlay.py
  - ../dotfiles/agent-profile/agent_profile/cli.py
---
# Profile launch projects policy without applying profiles

### ADR-004: Keep launch independent of apply state  [status: accepted]
- **Context:** Coupling launch to apply freshness would make per-process policy projection mutate persistent configuration. Isolated harnesses also need generated files after the CLI execs the harness.[^1]
- **Decision:** Build a complete secret-safe immutable `LaunchSpec` before exec; never require or mutate apply state. Unique mode-0700 workspaces use `XDG_RUNTIME_DIR`, then `XDG_CACHE_HOME`/`HOME/.cache`, with mode-0600 files. Exec failure cleans the new workspace; successful exec has no automatic cleanup. Copilot caller allow/deny flags are rejected.
- **Alternatives:** Launch-time apply creates hidden persistence; supervising a child changes exec/signal semantics; deterministic shared overlays allow stale state across launches.
- **Consequences:** Validation fails before exec and persistent deployment stays explicit. Cache-fallback runtime workspaces can remain after successful launch and are outside profile apply ownership.

[^1]: `../dotfiles/agent-profile/agent_profile/overlay.py:9-27,482-521`; `../dotfiles/agent-profile/agent_profile/cli.py:303-463`.
