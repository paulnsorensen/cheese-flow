set shell := ["bash", "-c", "set -euo pipefail; if r=$(rtk rewrite \"$0\" 2>/dev/null); then eval \"$r\"; else eval \"$0\"; fi"]

build:
    rm -rf dist coverage .claude .codex
    npm install
    npm run format
    npm run lint:fix
    npm run typecheck
    npm run build
    rtk test npm run test:coverage

build-ci:
    rm -rf dist coverage .claude .codex
    npm ci
    npm run format:check
    npm run lint:check
    npm run typecheck
    npm run build
    npm run test:coverage
