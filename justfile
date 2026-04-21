set shell := ["bash", "-euo", "pipefail", "-c"]

build:
    rm -rf dist coverage .claude .codex
    npm install
    npm run format
    npm run lint:fix
    npm run lint
    npm run build
    npm run test:coverage

build-ci:
    rm -rf dist coverage .claude .codex
    npm ci
    npm run format:check
    npm run lint:check
    npm run lint
    npm run build
    npm run test:coverage
