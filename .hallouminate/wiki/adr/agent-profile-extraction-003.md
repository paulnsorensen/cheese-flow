---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - ../dotfiles/agent-profile/agent_profile/apply_compiled.py
---
# Profile apply uses journaled recovery

### ADR-003: Journal profile apply before target mutation  [status: accepted]
- **Context:** Legacy copy/delete/state ordering can leave generated or deleted files absent from ownership state after exception or process death.[^1]
- **Decision:** Apply takes an exclusive state lock, completes generation/hash/path/ownership preflight, writes a private journal, atomically replaces desired files, deletes only bounded stale ownership, and commits schema-v1 state. Journal phases are `prepared`, `files_written`, and `stale_deleted`; recovery replays each idempotently before accepting another manifest.
- **Alternatives:** Final-state-only recording repeats ownership loss; resetting legacy ownership or deleting unclaimed paths can orphan or destroy user data; compatibility state prolongs two protocols.
- **Consequences:** Interrupted applies recover deterministically and tampered generations fail closed. V1 assumes a local non-adversarial filesystem, revalidates parent chains before mutation, and does not promise malicious-TOCTOU or sudden-power-loss safety.

[^1]: `../dotfiles/agent-profile/agent_profile/apply_compiled.py:260-288`.
