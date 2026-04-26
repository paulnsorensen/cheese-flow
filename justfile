set shell := ["bash", "-c", "set -euo pipefail; if r=$(rtk rewrite \"$0\" 2>/dev/null); then eval \"$r\"; else eval \"$0\"; fi"]

build:
    rm -rf dist coverage .claude .codex
    npm install
    npm run format
    npm run lint:fix
    npm run lint:skills
    npm run typecheck
    npm run build
    rtk test npm run test:coverage
    uv run --group dev ruff format
    uv run --group dev ruff check --fix
    uv run --group dev pytest

build-ci:
    rm -rf dist coverage .claude .codex
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

test-py:
    uv run --group dev pytest
