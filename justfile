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
    rm -rf dist coverage .claude .codex .cursor .copilot
    npm install
    npm run format
    npm run lint:fix
    npm run typecheck
    npm run build
    rtk test npm run test:coverage
    uv run --group dev ruff format
    uv run --group dev ruff check --fix
    uv run --group dev pytest
    @echo "Build passed - ready for PR"

# Full build no autofix: format check -> lint check -> typecheck -> build -> tests (for CI)
build-ci:
    rm -rf dist coverage .claude .codex .cursor .copilot
    npm ci
    npm run format:check
    npm run lint:check
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

# Clean build artifacts and caches
clean:
    rm -rf dist coverage .claude .codex .cursor .copilot
    rm -rf .pytest_cache .ruff_cache htmlcov .coverage node_modules/.cache
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
