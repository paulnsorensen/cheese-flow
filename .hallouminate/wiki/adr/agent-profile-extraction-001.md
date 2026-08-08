---
status: reviewed
last_verified: 2026-08-07
confidence: high
sources:
  - ../dotfiles/agent-profile/agent_profile/parse.py
  - ../dotfiles/agent-profile/agent_profile/renderers/
---
# Reusable profile behavior belongs to cheese-flow

### ADR-001: Separate the reusable engine from personal profile content  [status: accepted]
- **Context:** Dotfiles combines reusable parsing, validation, rendering, compilation, application, and launch projection with personal definitions and machine preparation. Cheese-flow installer abstractions describe component installation rather than profile deployment.[^1]
- **Decision:** Add a separate `cheese_flow.profiles` domain with explicit source-root and environment inputs. Cheese-flow owns reusable behavior, including explicit-root project-permission rendering; dotfiles retains personal sources, registries, bodies, preparation, wrappers, and the exact engine pin.
- **Alternatives:** Widening `InstallPlan`/`PlanStep`/`ComponentAdapter` conflates domains; moving personal content into cheese-flow reverses ownership; a dotfiles renderer duplicates the behavior being extracted.
- **Consequences:** The repositories gain a narrow contract and ordered rollout. Cheese-flow tests use fixtures and never discover dotfiles, vault, `.env`, or personal caches.

[^1]: `../dotfiles/agent-profile/agent_profile/parse.py`; `../dotfiles/agent-profile/agent_profile/renderers/`; `python/cheese_flow/models.py:394-412`.
