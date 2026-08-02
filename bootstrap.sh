#!/bin/sh
# One-line entry point for a bare host:
#
#   curl -fsSL https://raw.githubusercontent.com/paulnsorensen/cheese-flow/main/bootstrap.sh \
#     | sh -s -- --harness claude-code
#
# Installs uv when it is absent, then hands every argument to `cheese install`.
# Runs the wizard or installs headlessly, exactly as `cheese install` does when
# invoked directly: passing state options selects headless, passing none selects
# the wizard. Piping into `sh` consumes the stdin the wizard reads, so main()
# reconnects the terminal before exec — see the comment there.
set -eu

# Overridable so a smoke test can install the checkout under review. Left to its
# default this resolves to the repository's default branch, which is what the
# curl-pipe-sh line above wants and what a CI job testing a pull request must
# not get.
REPOSITORY="${CHEESE_REPOSITORY:-git+https://github.com/paulnsorensen/cheese-flow}"

main() {
    if ! command -v uvx >/dev/null 2>&1; then
        echo "cheese: installing uv" >&2
        # Bounded on purpose: a box with no egress to astral.sh blocks in
        # connect() with no timeout of its own, and this runs before the
        # installer's own per-command timeout exists to catch it.
        # `--proto '=https' --tlsv1.2` refuses a redirect that downgrades the
        # transport, the one hardening rustup's installer applies that the rest
        # of the field omits.
        # `>&2` because stdout belongs to `cheese install --json`. The uv
        # installer narrates its progress on stdout, which lands ahead of the
        # JSON document and breaks any caller piping this one-liner into a
        # parser — on precisely the bare hosts where uv has to be installed.
        curl -fsSL --proto '=https' --tlsv1.2 \
            --connect-timeout 10 --max-time 120 \
            https://astral.sh/uv/install.sh | sh >&2
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

    # Under `curl … | sh` this script *is* stdin, so the child inherits a pipe
    # sitting at EOF and the wizard's first read looks like the user quitting.
    # Reconnect the terminal so an argument-less run reaches the wizard. When
    # arguments select headless mode nothing reads stdin and this is inert, so
    # the decision stays in `cheese install` rather than being re-derived here.
    # No /dev/tty means no terminal exists; `cheese install` reports that with
    # the options that avoid the wizard. The open has to be attempted rather
    # than tested with `-r`, which passes on the mode bits of a /dev/tty that
    # no controlling terminal backs and then fails the redirect with ENXIO.
    if [ ! -t 0 ] && (exec </dev/tty) 2>/dev/null; then
        exec uvx --from "$REPOSITORY" cheese install "$@" </dev/tty
    fi
    exec uvx --from "$REPOSITORY" cheese install "$@"
}

# Called on the last line so a truncated download executes nothing: `sh` runs
# what it has read, and until this point that is only definitions.
main "$@"
