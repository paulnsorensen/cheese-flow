"""Tilth adapter: installs Tilth from the paulnsorensen/tilth nightly GitHub
release, then registers it with each selected harness's native config."""

from __future__ import annotations

import os
import platform
import shlex
from pathlib import Path

from cheese_flow.adapters.native_config import read_mcp_entry
from cheese_flow.models import (
    HARNESS_NAMES,
    CommandRunner,
    ComponentName,
    DesiredState,
    HarnessName,
    Phase,
    PlanStep,
)

PACKAGE = "tilth"

EDIT_FLAG = "--edit"
"""Edit mode is always requested, so ``--edit`` must be present in the entry."""

INSTALL_STEP = "tilth:install"

RELEASE_URL = "https://github.com/paulnsorensen/tilth/releases/download/nightly"
"""Rolling nightly release: no version pin. Integrity comes from the sidecar digest."""

_TRIPLE_VENDORS: dict[str, str] = {
    "Darwin": "apple-darwin",
    "Linux": "unknown-linux-musl",
}


def _target_triple() -> str:
    """The nightly release asset triple for the running platform."""
    system = platform.system()
    raw_machine = platform.machine()
    machine = "aarch64" if raw_machine == "arm64" else raw_machine
    vendor = _TRIPLE_VENDORS.get(system)
    if vendor is None or machine not in ("aarch64", "x86_64"):
        raise RuntimeError(f"could not resolve a tilth release asset for {system}/{raw_machine}")
    return f"{machine}-{vendor}"


def _bin_dir() -> Path:
    """Where the tilth binary is installed, honoring ``XDG_BIN_HOME`` like bootstrap.sh."""
    xdg_bin_home = os.environ.get("XDG_BIN_HOME")
    return Path(xdg_bin_home) if xdg_bin_home else Path.home() / ".local" / "bin"


def _install_script(triple: str, bin_dir: Path) -> str:
    """POSIX sh: bounded, retried download of the tarball and its sidecar, digest
    verification, and an atomic install."""
    tarball_url = f"{RELEASE_URL}/tilth-{triple}.tar.gz"
    sidecar_url = f"{tarball_url}.sha256"
    quoted_bin_dir = shlex.quote(str(bin_dir))
    return f"""set -eu
workdir="$(mktemp -d)"
staged=""
trap 'rm -rf "$workdir" "$staged"' EXIT

sha256_of() {{
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "cheese: no sha256sum or shasum available to verify tilth" >&2
        exit 1
    fi
}}

# Retry envelope covers the measured ~75s nightly-republish 404 window; worst
# case ~180s per curl, ~370s for the script.
curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 60 \\
    --retry 4 --retry-delay 15 --retry-all-errors --retry-max-time 120 \\
    -o "$workdir/tilth.tar.gz" '{tarball_url}' \\
    || {{ echo "cheese: could not download tilth for {triple} from {tarball_url}" >&2; exit 1; }}
curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 60 \\
    --retry 4 --retry-delay 15 --retry-all-errors --retry-max-time 120 \\
    -o "$workdir/tilth.tar.gz.sha256" '{sidecar_url}' \\
    || {{
        echo "cheese: could not download the checksum for tilth {triple} from {sidecar_url}" >&2
        exit 1
    }}

expected="$(cut -d' ' -f1 "$workdir/tilth.tar.gz.sha256")"
actual="$(sha256_of "$workdir/tilth.tar.gz")" || exit 1
[ -n "$actual" ] || {{ echo "cheese: could not hash the tilth download" >&2; exit 1; }}
if [ "$actual" != "$expected" ]; then
    echo "cheese: refusing to install tilth — checksum mismatch" >&2
    echo "  expected $expected" >&2
    echo "  actual   $actual" >&2
    echo "  url      {tarball_url}" >&2
    echo "  (a nightly republish mid-download is a likely benign cause; retry)" >&2
    exit 1
fi

tar -xzf "$workdir/tilth.tar.gz" -C "$workdir"
mkdir -p {quoted_bin_dir}
staged="$(mktemp {quoted_bin_dir}/tilth.XXXXXX)"
mv "$workdir/tilth" "$staged"
chmod +x "$staged"
mv "$staged" {quoted_bin_dir}/tilth
"""


def _launches_tilth(command: str) -> bool:
    """Whether an MCP entry launches Tilth's installed binary.

    ``tilth install`` writes the binary's own absolute path; a stale
    npm-era ``npx tilth`` entry no longer counts.
    """
    path = Path(command)
    return path.is_absolute() and path.name == PACKAGE


# Native user-scope MCP config per harness, relative to the home directory.
_CONFIG_PATHS: dict[HarnessName, str] = {
    "claude-code": ".claude.json",
    "codex": ".codex/config.toml",
    "cursor": ".cursor/mcp.json",
}


class TilthAdapter:
    """Installs Tilth from the nightly GitHub release, then registers its MCP
    server in each selected harness's native config."""

    name: ComponentName = "tilth"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Emit one install step and one register step per selected harness."""
        if self.name not in state.components:
            return ()
        triple = _target_triple()
        bin_dir = _bin_dir()
        binary = bin_dir / PACKAGE
        steps: list[PlanStep] = [
            PlanStep(
                step_id=INSTALL_STEP,
                component=self.name,
                phase=Phase.INSTALL,
                argv=("sh", "-c", _install_script(triple, bin_dir)),
                postcondition=f"`{binary} --version` exits 0",
            )
        ]
        steps.extend(
            PlanStep(
                step_id=f"tilth:register:{harness}",
                component=self.name,
                harness=harness,
                phase=Phase.REGISTER,
                argv=(str(binary), "install", harness, "--edit"),
                postcondition=(f"{_CONFIG_PATHS[harness]} holds the tilth MCP entry in edit mode"),
                depends_on=(INSTALL_STEP,),
            )
            for harness in HARNESS_NAMES
            if harness in state.harnesses
        )
        return tuple(steps)

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Confirm the installed binary runs, or the harness config holds the entry."""
        if step.step_id == INSTALL_STEP:
            binary = _bin_dir() / PACKAGE
            return runner.run((str(binary), "--version")).exit_code == 0
        if step.harness is None:
            raise ValueError(f"step {step.step_id!r} has no harness")
        entry = read_mcp_entry(Path.home() / _CONFIG_PATHS[step.harness], step.harness, PACKAGE)
        if not isinstance(entry, dict):
            return False
        args = entry.get("args")
        command = entry.get("command")
        if not isinstance(args, list) or not isinstance(command, str):
            return False
        args = [str(arg) for arg in args]
        return _launches_tilth(command) and "--mcp" in args and EDIT_FLAG in args
