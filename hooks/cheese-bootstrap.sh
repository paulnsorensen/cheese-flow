#!/usr/bin/env bash
set -euo pipefail

mkdir -p .cheese

if [ ! -f .gitignore ]; then
  : > .gitignore
fi

if ! grep -qxF '.cheese/' .gitignore; then
  if [ -s .gitignore ] && [ "$(tail -c1 .gitignore | od -An -c | tr -d ' ')" != "\n" ]; then
    printf '\n' >> .gitignore
  fi
  printf '%s\n' '.cheese/' >> .gitignore
fi

if command -v cheese >/dev/null 2>&1; then
  cheese session-start --root "$(pwd)" --quiet --max-time 5000 >/dev/null 2>&1 || true
fi

exit 0
