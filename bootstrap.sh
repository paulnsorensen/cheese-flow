#!/bin/sh
# One-line entry point for a bare host:
#
#   curl -fsSL https://raw.githubusercontent.com/paulnsorensen/cheese-flow/main/bootstrap.sh \
#     | sh -s -- --harness claude-code
#
# Installs uv when it is absent, then hands every argument to `cheese install`.
# Headless only by construction: piping this script into `sh` consumes stdin,
# which is what the interactive wizard reads. Pass the state options.
set -eu

# Overridable so a smoke test can install the checkout under review. Left to its
# default this resolves to the repository's default branch, which is what the
# curl-pipe-sh line above wants and what a CI job testing a pull request must
# not get.
REPOSITORY="${CHEESE_REPOSITORY:-git+https://github.com/paulnsorensen/cheese-flow}"

if ! command -v uvx >/dev/null 2>&1; then
    echo "cheese: installing uv" >&2
    # Bounded on purpose: a box with no egress to astral.sh blocks in connect()
    # with no timeout of its own, and this runs before the installer's own
    # per-command timeout exists to catch it.
    curl -fsSL --connect-timeout 10 --max-time 120 https://astral.sh/uv/install.sh | sh
    # The uv installer targets ~/.local/bin, which a non-login shell may not
    # already carry; without this, the exec below fails on the host we just
    # provisioned.
    PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH"
    export PATH
fi

# A pipeline's status is its last command's, and POSIX sh has no pipefail: a
# curl that 404s or times out leaves `| sh` exiting 0. Without this check the
# run dies further down as a bare "uvx: not found", naming the wrong failure.
if ! command -v uvx >/dev/null 2>&1; then
    echo "cheese: uv install failed; install uv and re-run — https://docs.astral.sh/uv/" >&2
    exit 1
fi

exec uvx --from "$REPOSITORY" cheese install "$@"
