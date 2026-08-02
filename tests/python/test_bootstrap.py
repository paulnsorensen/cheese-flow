"""Black-box tests for ``bootstrap.sh``, the curl-pipe-sh entry point.

The script runs for real; only the executables it reaches for are shimmed.
Each shim records its own argv, so the test asserts what would actually have
run on a host that has nothing but curl.
"""

from __future__ import annotations

import os
import pty
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
# The real installer narrates on stdout; reproduce that so the stream the
# one-liner hands to a JSON parser is actually under test.
echo "installing to $HOME/.local/bin"
echo "everything's installed!"
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
    tmp_path: Path, *args: str, path: Path, home: Path, repository: str | None = None
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
    env.pop("CHEESE_REPOSITORY", None)
    if repository is not None:
        env["CHEESE_REPOSITORY"] = repository
    completed = subprocess.run(
        ["/bin/sh", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return completed, record.read_text(encoding="utf-8").splitlines()


def _run(
    tmp_path: Path, *args: str, path: Path, home: Path, repository: str | None = None
) -> list[str]:
    completed, ran = _invoke(tmp_path, *args, path=path, home=home, repository=repository)
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
        f"{bin_dir / 'curl'} -fsSL --proto =https --tlsv1.2 --connect-timeout 10 --max-time 120 "
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
        f"{bin_dir / 'curl'} -fsSL --proto =https --tlsv1.2 --connect-timeout 10 --max-time 120 "
        "https://astral.sh/uv/install.sh"
    ]


def test_stdout_carries_only_the_installs_own_output(tmp_path: Path) -> None:
    """`--json` is the documented headless interface, so nothing may precede it.

    The uv installer narrates on stdout. Left there it lands ahead of the JSON
    document and breaks any caller piping the one-liner into a parser — only on
    the bare hosts that need uv installed, which is where it matters most.
    """
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)
    # The generated uvx echoes a JSON-ish document, standing in for the report.
    completed, _ = _invoke(tmp_path, "--json", path=bin_dir, home=tmp_path / "home")

    assert completed.returncode == 0, completed.stderr
    assert "installing to" not in completed.stdout
    assert "everything's installed" not in completed.stdout


def test_cheese_repository_overrides_the_default_source(tmp_path: Path) -> None:
    """Without this the smoke job installs the default branch and passes on code
    nobody is reviewing — a green gate that never saw the change."""
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "uvx")
    _shim(bin_dir, "curl")

    ran = _run(
        tmp_path,
        "--harness",
        "codex",
        path=bin_dir,
        home=tmp_path / "home",
        repository="/srv/checkout",
    )

    assert ran == [f"{bin_dir / 'uvx'} --from /srv/checkout cheese install --harness codex"]


def test_a_truncated_download_executes_nothing(tmp_path: Path) -> None:
    """`curl … | sh` runs whatever bytes arrived, so a dropped connection must be inert.

    Cut the transfer after the uv block and the pre-``main()`` script installed
    uv, never reached the exec, and exited 0 — a silent partial install that a
    caller parsing ``--json`` reads as success with empty stdout.
    """
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    # Everything up to and including the uv install, minus the call on the last line.
    cutoff = source.index('    if ! command -v uvx >/dev/null 2>&1; then\n        echo "cheese: uv')
    truncated = tmp_path / "truncated.sh"
    truncated.write_text(source[:cutoff], encoding="utf-8")

    record = tmp_path / "record"
    record.touch()
    home = tmp_path / "home"
    home.mkdir()
    completed = subprocess.run(
        ["/bin/sh", str(truncated)],
        capture_output=True,
        text=True,
        env=dict(os.environ)
        | {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), "RECORD": str(record)},
        check=False,
    )

    # An unterminated main() is a parse error, so nothing in it ever runs.
    assert completed.returncode != 0
    assert record.read_text(encoding="utf-8") == ""
    assert not (home / ".local" / "bin" / "uvx").exists()


def test_reconnects_the_terminal_so_a_piped_run_can_still_reach_the_wizard(tmp_path: Path) -> None:
    """The wizard reads stdin, and `curl … | sh` leaves the child a pipe at EOF.

    Without the /dev/tty reconnect an argument-less one-liner reports "Cancelled"
    and installs nothing, because the wizard's first read looks like a user quit.
    """
    bin_dir = tmp_path / "bin"
    _shim(
        bin_dir,
        "uvx",
        "#!/bin/sh\nif [ -t 0 ]; then printf 'stdin=tty\\n' >> \"$RECORD\";"
        " else printf 'stdin=pipe\\n' >> \"$RECORD\"; fi\n",
    )
    record = tmp_path / "record"
    record.touch()
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ) | {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "RECORD": str(record),
    }
    env.pop("CHEESE_REPOSITORY", None)

    # pty.fork gives the child a controlling terminal, so /dev/tty resolves;
    # stdin is then replaced with a spent pipe, which is what `curl … | sh` hands over.
    pid, master = pty.fork()
    if pid == 0:  # pragma: no cover - replaced by exec in the child
        read_end, write_end = os.pipe()
        os.close(write_end)
        os.dup2(read_end, 0)
        os.execve("/bin/sh", ["/bin/sh", str(SCRIPT_PATH)], env)
    # Drain to EOF before reaping: closing the master first hangs up the child's
    # terminal, killing it with SIGHUP before it can exec.
    while True:
        try:
            if not os.read(master, 1024):
                break
        except OSError:
            break
    os.close(master)
    _, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert record.read_text(encoding="utf-8").splitlines() == ["stdin=tty"]


def test_the_entry_point_is_executable_and_reaches_for_no_github_cli() -> None:
    """The whole point: the one-liner works on a host that has no `gh`."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gh " not in source
    assert SCRIPT_PATH.stat().st_mode & stat_mod.S_IXUSR
