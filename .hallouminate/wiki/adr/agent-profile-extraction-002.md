---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - ../dotfiles/agent-profile/agent_profile/compile_command.py
---
# Profile compilation publishes immutable generations

### ADR-002: Publish content-addressed compile generations  [status: accepted]
- **Context:** The legacy compiler removes current fragments before rendering and publishes `manifest.json` last, so a failed render can invalidate the previously usable publication.[^1]
- **Decision:** Schema-v1 manifests contain a 64-lowercase-hex `generation`. Its SHA-256 covers the canonical generation-relative descriptor and ordered fragment hashes. Compile renders privately, validates, publishes `generations/<generation>/` once, then atomically replaces the root manifest.
- **Alternatives:** Implicit path-derived identity hides the invariant; manifest-byte hashing alone does not bind directory identity; a mutable fragments directory preserves the failure window.
- **Consequences:** Identical canonical inputs yield the same generation and byte-equivalent manifest. Failed compilation leaves the prior publication usable. Output-root lifecycle and generation cleanup remain caller-owned.

[^1]: `../dotfiles/agent-profile/agent_profile/compile_command.py:180-183,242-253`.
