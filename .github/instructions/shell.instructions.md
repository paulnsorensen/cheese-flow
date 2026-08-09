---
applyTo: "**/*.sh"
---
- Use `set -euo pipefail` at the top of bash scripts (`bootstrap.sh` is POSIX `sh` — keep it POSIX-compatible; no bashisms there).
- Quote all variable expansions: `"$var"`, not `$var`.
- Use `[[ ]]` over `[ ]` in bash scripts; plain `[ ]` in POSIX `sh`.
- Use functions for any logic that repeats or exceeds 10 lines; `local` for function variables in bash.
- Fail loudly: check command exit status, and never pipe a download into execution without verifying its hash first.
- Prefer `printf` over `echo` for portable output.
