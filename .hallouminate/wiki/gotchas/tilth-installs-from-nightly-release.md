# Tilth installs from the paulnsorensen/tilth nightly release — npm `tilth` is someone else's package

The npm package `tilth` declares `repository: github.com/jahala/tilth` — a different publisher. cheese-flow's TilthAdapter therefore does **not** use npm/npx: it downloads the platform-triple binary (`tilth-<triple>.tar.gz` + `.sha256` sidecar) from `https://github.com/paulnsorensen/tilth/releases/download/nightly/`, verifies the digest, and installs atomically into `${XDG_BIN_HOME:-$HOME/.local/bin}` (PR stacked on #94).

## Decisions (user-locked, don't relitigate)

- **Rolling nightly, sidecar integrity, no pinning** — a nightly cannot be content-pinned like the uv installer; the `.sha256` sidecar over pinned TLS is the bar.
- **Install-once** — postcondition is "installed binary runs `--version` exit 0". No digest drift-chasing: `cheese doctor` must not go red every morning a nightly publishes. Upgrade = remove the binary and re-run.
- **Stale `npx tilth` entries are rejected** by `_launches_tilth` on purpose — accepting them would leave harnesses launching the foreign npm package forever.

## The republish window (measured 2026-08-02)

The nightly workflow deletes and re-uploads assets around ~19:00Z: each asset 404s for ~75s+ even while the API reports it `uploaded`. Hence both curls carry `--retry 4 --retry-delay 15 --retry-all-errors --retry-max-time 120 --max-time 60` (plain `--retry` does NOT retry 404s; `--max-time` is per attempt, so the envelope, not the flag, bounds wall clock: ~180s/curl, ~370s/script — smoke's per-step `--timeout 420` and the 900s runner default both fit). A digest mismatch during the window surfaces as a refusal naming the republish race — a sidecar re-fetch was tried and removed: the sidecar downloads after the tarball, so it is always at least as fresh and cannot rescue the race.

## Requirements this created

- curl ≥ 7.71 (`--retry-all-errors`), `tar`, `sha256sum` or `shasum` — named in README prerequisites.
- `${XDG_BIN_HOME:-$HOME/.local/bin}` on PATH for the dev-time `.mcp.json` entry (`command: tilth`); harness configs are immune — registration writes the absolute path.
