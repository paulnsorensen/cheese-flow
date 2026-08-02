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

# The uv installer this script is willing to execute. Pinned by version *and*
# content hash: a compromised or swapped astral.sh would otherwise run arbitrary
# code as the user, and this is the one place where that code is not ours.
#
# The version belongs in the URL. Astral serves the unversioned
# /uv/install.sh from whatever release is current, so a hash pinned against it
# breaks for every user on every uv release; /uv/<version>/install.sh is frozen,
# so this hash changes only when the version above it does.
#
# AGENTS.md § Pinned uv installer carries the refresh procedure.
UV_VERSION="0.12.1"
UV_INSTALLER_SHA256="d3f5412d38c99f9d024901843bf98206f0d2c6dbe64df40d0b740e2751ca62c1"

# Prints the SHA-256 of "$1" as a bare hex digest. GNU coreutils ships
# sha256sum; macOS ships shasum and no sha256sum.
sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "cheese: no sha256sum or shasum available to verify the uv installer" >&2
        return 1
    fi
}

# Downloads the pinned uv installer, refuses to run it unless it hashes as
# expected, and executes it only then.
install_uv() {
    installer="$(mktemp)" || return 1
    # The verified copy must not outlive this function on any exit path.
    trap 'rm -f "$installer"' EXIT
    # Bounded on purpose: a box with no egress to astral.sh blocks in connect()
    # with no timeout of its own, and this runs before the installer's own
    # per-command timeout exists to catch it.
    # `--proto '=https' --tlsv1.2` refuses a redirect that downgrades the
    # transport, which matters here because the versioned URL redirects.
    curl -fsSL --proto '=https' --tlsv1.2 \
        --connect-timeout 10 --max-time 120 \
        -o "$installer" \
        "https://astral.sh/uv/${UV_VERSION}/install.sh" || return 1

    actual="$(sha256_of "$installer")" || return 1
    if [ "$actual" != "$UV_INSTALLER_SHA256" ]; then
        echo "cheese: refusing to run the uv installer — it is not the pinned copy." >&2
        echo "  expected $UV_INSTALLER_SHA256" >&2
        echo "  actual   $actual" >&2
        echo "  url      https://astral.sh/uv/${UV_VERSION}/install.sh" >&2
        echo "Install uv yourself (https://docs.astral.sh/uv/) or report this —" >&2
        echo "a frozen versioned URL should never change content." >&2
        return 1
    fi

    # `>&2` because stdout belongs to `cheese install --json`. The uv installer
    # narrates its progress on stdout, which lands ahead of the JSON document
    # and breaks any caller piping this one-liner into a parser — on precisely
    # the bare hosts where uv has to be installed.
    sh "$installer" >&2
    status=$?
    # Cleared here rather than left to the trap: main() ends in `exec`, which
    # replaces the process image without running EXIT traps, so the success
    # path would otherwise leak the download.
    rm -f "$installer"
    trap - EXIT
    return $status
}

main() {
    if ! command -v uvx >/dev/null 2>&1; then
        echo "cheese: installing uv ${UV_VERSION}" >&2
        install_uv || true
        # The uv installer targets ~/.local/bin, which a non-login shell may not
        # already carry; without this, the exec below fails on the host we just
        # provisioned.
        PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH"
        export PATH
    fi

    # install_uv reports its own failures, and a uv installer that exits 0
    # without dropping a binary would report nothing at all. Check for the tool
    # rather than trusting either, so the run never dies further down as a bare
    # "uvx: not found", naming the wrong failure.
    if ! command -v uvx >/dev/null 2>&1; then
        echo "cheese: uv install failed; install uv and re-run — https://docs.astral.sh/uv/" >&2
        exit 1
    fi

    # git has no read timeout of its own: a proxied host that accepts the
    # connection and then stalls hangs the uvx clone below forever, before
    # `cheese install`'s own per-command timeout exists to catch it. Exporting
    # rather than flagging means every git the install tree runs — this clone
    # and every child clone `cheese install` runs later — inherits the bound.
    # `:-` defaults keep a caller's own tuning authoritative.
    GIT_HTTP_LOW_SPEED_LIMIT="${GIT_HTTP_LOW_SPEED_LIMIT:-1000}"
    GIT_HTTP_LOW_SPEED_TIME="${GIT_HTTP_LOW_SPEED_TIME:-30}"
    export GIT_HTTP_LOW_SPEED_LIMIT GIT_HTTP_LOW_SPEED_TIME

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
