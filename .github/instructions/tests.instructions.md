---
applyTo: "tests/**/*.py,tests/**/*.feature"
excludeAgent: "cloud-agent"
---

## pytest / pytest-bdd test review

Unit tests live under `tests/python/` with Gherkin features in `tests/python/features/`, shared fixtures in `tests/python/fixtures/`, and the smoke-install assertion in `tests/smoke/` (driven by `just smoke`, which runs a real bounded `bootstrap.sh` install into a throwaway HOME).

Flag as weak — a test that passes even when the code is broken:

- No assertions, or existence/no-crash-only checks
- Tautological assertions, and mirror-implementation tests that re-derive the expected value from the same logic as the system under test
- Mock echo tests — asserting a mock returned what the mock was told to return
- Assertions behind conditional branches that silently pass when the branch is skipped
- Happy-path-only coverage — no error or boundary case for the behavior under test
- `len()`-only collection checks where content matters
- Mocking the system under test
- Installer tests that assert a step was *attempted* without asserting the resulting on-disk state

Do not flag: sandboxed throwaway-HOME fixtures and subprocess doubles — they are the sanctioned way to exercise install flows without touching the real home directory; naming/style consistent with existing tests.

A test that needs its own uv installer accepted must rewrite the pin constant in a **copy** of `bootstrap.sh` — never via a bypass knob in the script itself.
