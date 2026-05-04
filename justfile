set shell := ["bash", "-c", "set -euo pipefail; if r=$(rtk rewrite \"$0\" 2>/dev/null); then eval \"$r\"; else eval \"$0\"; fi"]
set dotenv-load := false

# Show all available recipes
default:
    @just --list

# Install all dependencies (npm + uv)
install:
    npm install
    uv sync --group dev

# Full build with autofix: format -> lint -> typecheck -> build -> tests (for devs before PRs)
build:
    rm -rf dist coverage
    npm install
    npm run format
    npm run lint:fix
    npm run lint:skills
    npm run typecheck
    npm run build
    just _test-coverage
    uv run --group dev ruff format
    uv run --group dev ruff check --fix
    uv run --group dev pytest
    @echo "Build passed - ready for PR"

# Private build helper for optional rtk coverage wrapping.
[private]
_test-coverage:
    if command -v rtk >/dev/null 2>&1 \
        && rtk test --help >/dev/null 2>&1; then \
        rtk test npm run test:coverage; \
    else \
        npm run test:coverage; \
    fi

# Full build no autofix: format check -> lint check -> typecheck -> build -> tests (for CI)
build-ci:
    rm -rf dist coverage
    npm ci
    npm run format:check
    npm run lint:check
    npm run lint:skills
    npm run typecheck
    npm run build
    npm run test:coverage
    uv run --group dev ruff format --check
    uv run --group dev ruff check
    uv run --group dev pytest
    @echo "CI build passed"

# Run the TypeScript test suite (passes args through to vitest)
test *args:
    npm run test -- {{args}}

# Run the Python test suite (passes args through to pytest)
test-py *args:
    uv run --group dev pytest {{args}}

# Run /age fixture comparator against every dim under tests/age-fixtures/
test-age-fixtures:
    #!/usr/bin/env bash
    set -euo pipefail
    fixtures_dir="tests/age-fixtures"
    if [ ! -d "$fixtures_dir" ]; then
        echo "no fixtures directory at $fixtures_dir" >&2
        exit 1
    fi
    shopt -s nullglob
    dim_dirs=("$fixtures_dir"/*/)
    if [ "${#dim_dirs[@]}" -eq 0 ]; then
        echo "no fixture subdirectories found under $fixtures_dir" >&2
        exit 1
    fi
    failures=0
    for dim_dir in "${dim_dirs[@]}"; do
        dim=$(basename "$dim_dir")
        expected="$dim_dir/expected.json"
        actual="$dim_dir/actual.json"
        if [ ! -f "$expected" ]; then
            echo "$dim: missing expected.json" >&2
            failures=$((failures + 1))
            continue
        fi
        if [ ! -f "$actual" ]; then
            echo "$dim: missing actual.json (run /age first to populate)" >&2
            failures=$((failures + 1))
            continue
        fi
        if uv run python python/tools/age_fixture_diff.py "$actual" "$expected"; then
            echo "$dim: ok"
        else
            echo "$dim: FAIL" >&2
            failures=$((failures + 1))
        fi
    done
    if [ "$failures" -gt 0 ]; then
        echo "$failures fixture(s) failed" >&2
        exit 1
    fi

# Run /skill-improver fixture comparator against every dim under tests/skill-improver-fixtures/
test-skill-improver-fixtures:
    #!/usr/bin/env bash
    set -euo pipefail
    fixtures_dir="tests/skill-improver-fixtures"
    if [ ! -d "$fixtures_dir" ]; then
        echo "no fixtures directory at $fixtures_dir" >&2
        exit 1
    fi
    shopt -s nullglob
    dim_dirs=("$fixtures_dir"/*/)
    if [ "${#dim_dirs[@]}" -eq 0 ]; then
        echo "no fixture subdirectories found under $fixtures_dir" >&2
        exit 1
    fi
    failures=0
    for dim_dir in "${dim_dirs[@]}"; do
        dim=$(basename "$dim_dir")
        expected="$dim_dir/expected.json"
        actual="$dim_dir/actual.json"
        if [ ! -f "$expected" ]; then
            echo "$dim: missing expected.json" >&2
            failures=$((failures + 1))
            continue
        fi
        if [ ! -f "$actual" ]; then
            echo "$dim: missing actual.json (run /skill-improver first to populate)" >&2
            failures=$((failures + 1))
            continue
        fi
        if uv run python python/tools/age_fixture_diff.py "$actual" "$expected"; then
            echo "$dim: ok"
        else
            echo "$dim: FAIL" >&2
            failures=$((failures + 1))
        fi
    done
    if [ "$failures" -gt 0 ]; then
        echo "$failures fixture(s) failed" >&2
        exit 1
    fi
# Clean build artifacts and caches
clean:
    rm -rf dist coverage
    rm -rf .pytest_cache .ruff_cache htmlcov .coverage node_modules/.cache
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
