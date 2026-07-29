---
status: reviewed
last_verified: 2026-07-29
confidence: high
sources:
  - .cheese/notes/cheese-ecosystem-composition.md
  - pyproject.toml
---
# Cheese-flow v1 is a composition installer

Cheese-flow v1 replaces the pre-release compiler platform with a thin installer that delegates to independent products. It does not host a unified MCP, compile portable agents, or embed Milknado.[^1]

## Context

The existing package combines compiler, harness installer, Milknado, and MCP responsibilities. Its runtime dependencies include MCP and Milknado, its CLI exposes compile and MCP commands, and its adapter registry models emitted bundles rather than component installation.[^2]

The accepted product goal is one install experience for Hallouminate and easy-cheese, with Tilth optional. Each component already owns a native installer and runtime.[^3]

## Decision

- Keep the `cheese-flow` package, the `cheese` command, and the Cheese Flow TUI title.
- Remove compiler, portable-agent, Milknado, and unified-MCP behavior without migration code.
- Delegate every install, registration, and verification operation through a component adapter that invokes the native CLI.
- Support Claude Code, Codex, and Cursor in v1.
- Require Hallouminate and easy-cheese; offer Tilth unchecked.

## Alternatives

- Retaining the compiler preserves incompatible concepts and public seams that the new product does not need.
- A unified MCP couples independent runtimes and contradicts their native lifecycle ownership.
- Importing component internals creates a second integration contract without eliminating native installers.

## Consequences

The package and test suite receive a broad replacement, but the resulting boundary is smaller. Component releases remain independent. Cross-component rollback is not promised, and harness expansion becomes explicit adapter work.

## References

[^1]: `.cheese/notes/cheese-ecosystem-composition.md:22-35`.
[^2]: `pyproject.toml:7-19,31-32`; `python/cheese_flow/cli.py:60-222`; `python/cheese_flow/adapters/__init__.py:9-22`.
[^3]: `.cheese/research/cheese-flow-v1-installer/cheese-flow-v1-installer.md:21-57`.
