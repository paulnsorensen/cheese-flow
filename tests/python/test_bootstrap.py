"""Black-box tests for ``bootstrap.sh``, the curl-pipe-sh entry point.

The script runs for real; only the executables it reaches for are shimmed.
Each shim records its own argv, so the test asserts what would actually have
run on a host that has nothing but curl.
"""

from __future__ import annotations

import os
import stat as stat_mod
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "bootstrap.sh"

FROM = "--from git+https://github.com/paulnsorensen/cheese-flow"

RECORDING_SHIM = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$RECORD"
"""

# Stands in for https://astral.sh/uv/install.sh: the script bootstrap.sh pipes
# into `sh`, which drops uv where a non-login shell cannot see it yet.
UV_INSTALLER_SHIM = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$RECORD"
cat <<'INSTALLER'
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uvx" <<'UVX'
#!/bin/sh
printf '%s\\n' "installed-uvx $*" >> "$RECORD"
UVX
chmod +x "$HOME/.local/bin/uvx"
INSTALLER
"""


def _shim(directory: Path, name: str, body: str = RECORDING_SHIM) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / name
    shim.write_text(body, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return shim


def _invoke(
    tmp_path: Path, *args: str, path: Path, home: Path
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the script with ``path`` at the head of ``PATH``; return it and what ran."""
    record = tmp_path / "record"
    record.touch()
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ) | {
        # The system directories keep `sh` itself resolvable; nothing the
        # script looks for lives there.
        "PATH": f"{path}:/usr/bin:/bin",
        "HOME": str(home),
        "RECORD": str(record),
    }
    env.pop("XDG_BIN_HOME", None)
    completed = subprocess.run(
        ["/bin/sh", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return completed, record.read_text(encoding="utf-8").splitlines()


def _run(tmp_path: Path, *args: str, path: Path, home: Path) -> list[str]:
    completed, ran = _invoke(tmp_path, *args, path=path, home=home)
    assert completed.returncode == 0, completed.stderr
    return ran


def test_hands_every_argument_to_a_headless_cheese_install(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "uvx")
    _shim(bin_dir, "curl")

    ran = _run(
        tmp_path,
        "--harness",
        "claude-code",
        "--repo",
        "/srv/code/project",
        path=bin_dir,
        home=tmp_path / "home",
    )

    assert ran == [
        f"{bin_dir / 'uvx'} {FROM} cheese install --harness claude-code --repo /srv/code/project"
    ]


def test_installs_uv_first_when_the_host_has_none_and_then_runs_it(tmp_path: Path) -> None:
    """The bare cloud box: curl, git, and node. uv has to arrive before anything else."""
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)

    ran = _run(tmp_path, "--harness", "codex", path=bin_dir, home=tmp_path / "home")

    # `uvx` existed nowhere on PATH, so reaching it at all proves the script
    # both installed uv and put its target directory on PATH.
    assert ran == [
        f"{bin_dir / 'curl'} -fsSL --connect-timeout 10 --max-time 120 "
        "https://astral.sh/uv/install.sh",
        f"installed-uvx {FROM} cheese install --harness codex",
    ]


def test_a_failed_uv_install_stops_the_run_and_names_the_real_failure(tmp_path: Path) -> None:
    """`curl … | sh` exits 0 when curl fails, so the download must be checked, not assumed.

    Without the check the run continues to `exec uvx` and dies as `uvx: not
    found`, blaming the wrong thing on a host where nothing was installed.
    """
    bin_dir = tmp_path / "bin"
    # A curl that resolves nothing: the pipeline still exits 0, and no uv appears.
    _shim(bin_dir, "curl")

    completed, ran = _invoke(tmp_path, "--harness", "codex", path=bin_dir, home=tmp_path / "home")

    assert completed.returncode == 1
    assert "uv install failed" in completed.stderr
    assert ran == [
        f"{bin_dir / 'curl'} -fsSL --connect-timeout 10 --max-time 120 "
        "https://astral.sh/uv/install.sh"
    ]


def test_the_entry_point_is_executable_and_reaches_for_no_github_cli() -> None:
    """The whole point: the one-liner works on a host that has no `gh`."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gh " not in source
    assert SCRIPT_PATH.stat().st_mode & stat_mod.S_IXUSR
