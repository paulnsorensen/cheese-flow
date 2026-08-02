# Pytest-BDD scenarios

Gherkin scenarios run through the existing pytest test path. The prototype uses `pytest-bdd` 8.1.0 as a development dependency, so `just build` and `just build-ci` need no second runner.[^1]

## Prototype scope

The first scenario specifies easy-cheese installation on a host without the GitHub CLI. Its Python steps exercise the real headless installer, with only the child-process boundary faked through the existing integration-test `GhlessWorld`.[^2]

The feature file describes the outcome. Step definitions retain exact command and result assertions. This keeps the specification readable without weakening the pre-existing integration behavior.[^2]

## CI

GitHub Actions invokes `just build-ci`, which runs pytest. The CI step explicitly identifies that it includes Gherkin scenarios.[^3]

## Platform-aware tests

Repository paths are deliberately canonicalized. Manifest tests must compare their expected paths after `Path.resolve()`, because macOS can resolve `/home` through its data-volume prefix.[^4]

The descriptor and zombie inspection test relies on Linux `/proc`; it skips where that filesystem is unavailable rather than asserting an OS-specific implementation detail.[^5]

[^1]: pyproject.toml:16-34; justfile:13-28; uv.lock:41-59
[^2]: tests/python/features/easy_cheese.feature:1-6; tests/python/test_integration.py:905-948
[^3]: .github/workflows/ci.yml:27-28
[^4]: python/cheese_flow/models.py:110-119; tests/python/test_desired_state.py:113-124,289-304,365-378
[^5]: tests/python/test_runner.py:248-282
