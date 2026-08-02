# Git has no read timeout — the install tree bounds it via GIT_HTTP_LOW_SPEED_*

`git fetch`/`clone` waits forever on a connection that is accepted and then stalls (verified empirically against an accept-then-silent server). Behind a filtering egress proxy — Claude Code on the web's sandbox is the motivating case — this hung the bootstrap one-liner unbounded, *before* `cheese install`'s per-command timeout existed to catch it (PR #94, diagnosis in `.cheese/pasteurize/cloud-setup-hang.md`).

## The invariant

Every git the install tree runs must inherit `GIT_HTTP_LOW_SPEED_LIMIT` / `GIT_HTTP_LOW_SPEED_TIME` (defaults 1000 B/s over 30 s). It lives in **two deliberate places** — unavoidable across the sh/Python boundary, cross-referenced in comments:

- `bootstrap.sh` `main()` — covers the `uvx --from git+…` clone the script execs, which the runner can never reach.
- `cli.py` `_default_runner` — covers child clones (`claude plugin marketplace add`, `npx skills add`) from **every** entry point: bootstrap, checkout, direct `uvx`, and `doctor`.

## Semantics that matter

- **Caller wins**: both sites treat a caller-set value as authoritative. `SubprocessRunner._environment` is `{**os.environ, **self._env}`, so the runner must inject only-if-absent — a plain overlay would clobber the caller.
- **Empty counts as absent** (`not os.environ.get(key)`, matching `${VAR:-}`): git parses an exported-but-empty value as an error, warns, and silently disables the guard.
- uv runs its git with terminal prompts disabled, so the `/dev/tty` reconnect (#92) cannot cause a credential-prompt hang — falsified hypothesis, don't re-investigate.

## Known residual

The pinned uv installer's *internal* curl (inside the SHA-pinned `astral.sh` script) has no `--max-time` — the pre-`cheese install` window is not fully closed. POSIX sh has no watchdog and macOS lacks `timeout(1)`; accepted as residual, not a fixable-here bug.

## Cloud-sandbox facts (primary-sourced, 2026-08)

Research slug: `.cheese/research/claude-code-cloud-setup-sandbox/`. Highlights: `astral.sh` is NOT on the default package-manager allowlist (github.com, objects.githubusercontent.com, pypi.org are); setup scripts get a ~5-minute soft budget and must exit 0; setup stdout/stderr is not retrievable afterwards. Hence README's advice to append `--timeout 90` on time-budgeted sandbox setups.
