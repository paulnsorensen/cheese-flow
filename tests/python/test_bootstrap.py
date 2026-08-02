"""Black-box tests for ``bootstrap.sh``, the curl-pipe-sh entry point.

The script runs for real; only the executables it reaches for are shimmed.
Each shim records its own argv, so the test asserts what would actually have
run on a host that has nothing but curl.
"""

from __future__ import annotations

import hashlib
import os
import pty
import re
import stat as stat_mod
import subprocess
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "bootstrap.sh"


def _pinned_version() -> str:
    match = re.search(r'UV_VERSION="([^"]+)"', SCRIPT_PATH.read_text(encoding="utf-8"))
    assert match, "bootstrap.sh no longer declares UV_VERSION"
    return match.group(1)


FROM = "--from git+https://github.com/paulnsorensen/cheese-flow"

RECORDING_SHIM = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$RECORD"
"""

# The uv installer bootstrap.sh downloads, verifies, and runs. Written to the
# path curl was given rather than to stdout, because the script hashes the file
# before executing it.
UV_INSTALLER_BODY = """# The real installer narrates on stdout; reproduce that so the stream the
# one-liner hands to a JSON parser is actually under test.
echo "installing to $HOME/.local/bin"
echo "everything's installed!"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uvx" <<'UVX'
#!/bin/sh
printf '%s\\n' "installed-uvx $*" >> "$RECORD"
UVX
chmod +x "$HOME/.local/bin/uvx"
"""

# Stands in for https://astral.sh/uv/<version>/install.sh. Records its argv and
# writes $INSTALLER_BODY to the -o target, the way the real curl invocation does.
UV_INSTALLER_SHIM = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$RECORD"
target=""
while [ $# -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        target="$2"
        break
    fi
    shift
done
[ -n "$target" ] || exit 1
printf '%s' "$INSTALLER_BODY" > "$target"
"""


# Records $0, argv, and the two git low-speed env vars the exec'd child must
# see — argv alone can't show whether bootstrap.sh exported them.
GIT_ENV_SHIM = """#!/bin/sh
limit="${GIT_HTTP_LOW_SPEED_LIMIT:-unset}"
low_speed_time="${GIT_HTTP_LOW_SPEED_TIME:-unset}"
record="$0 $* GIT_HTTP_LOW_SPEED_LIMIT=$limit GIT_HTTP_LOW_SPEED_TIME=$low_speed_time"
printf '%s\\n' "$record" >> "$RECORD"
"""


def _shim(directory: Path, name: str, body: str = RECORDING_SHIM) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / name
    shim.write_text(body, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return shim


def _pinned_to(tmp_path: Path, body: str) -> Path:
    """Copy the script with its uv-installer pin set to the hash of ``body``.

    The pin is deliberately not overridable at runtime — an env knob that skips
    verification is exactly the bypass the pin exists to prevent — so a test that
    wants its own installer accepted has to rewrite the constant.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(body.encode()).hexdigest()
    patched = re.sub(
        r'UV_INSTALLER_SHA256="[0-9a-f]{64}"', f'UV_INSTALLER_SHA256="{digest}"', source, count=1
    )
    assert patched != source, "the pin constant moved; this helper no longer patches it"
    script = tmp_path / "pinned.sh"
    script.write_text(patched, encoding="utf-8")
    return script


def _invoke(
    tmp_path: Path,
    *args: str,
    path: Path,
    home: Path,
    repository: str | None = None,
    script: Path | None = None,
    installer_body: str = UV_INSTALLER_BODY,
    env_overrides: Mapping[str, str] | None = None,
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
        "INSTALLER_BODY": installer_body,
    }
    env.pop("XDG_BIN_HOME", None)
    env.pop("CHEESE_REPOSITORY", None)
    env.pop("GIT_HTTP_LOW_SPEED_LIMIT", None)
    env.pop("GIT_HTTP_LOW_SPEED_TIME", None)
    if repository is not None:
        env["CHEESE_REPOSITORY"] = repository
    if env_overrides is not None:
        env.update(env_overrides)
    completed = subprocess.run(
        ["/bin/sh", str(script or SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return completed, record.read_text(encoding="utf-8").splitlines()


def _run(
    tmp_path: Path,
    *args: str,
    path: Path,
    home: Path,
    repository: str | None = None,
    script: Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    completed, ran = _invoke(
        tmp_path,
        *args,
        path=path,
        home=home,
        repository=repository,
        script=script,
        env_overrides=env_overrides,
    )
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


def test_exports_git_low_speed_abort_for_the_exec_child(tmp_path: Path) -> None:
    """git has no read timeout of its own; the uvx clone (and every child clone
    `cheese install` runs later) must abort a stalled transfer instead of
    hanging forever, before `cheese install`'s own timeout exists to catch it."""
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "uvx", GIT_ENV_SHIM)
    _shim(bin_dir, "curl")

    ran = _run(
        tmp_path,
        "--harness",
        "claude-code",
        path=bin_dir,
        home=tmp_path / "home",
    )

    assert ran == [
        f"{bin_dir / 'uvx'} {FROM} cheese install --harness claude-code "
        "GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30"
    ]


def test_preserves_caller_supplied_git_low_speed_bounds(tmp_path: Path) -> None:
    """A caller's own tuning stays authoritative; only the missing half fills
    in. Overrides TIME only, so this also covers TIME-override (LIMIT-override
    coverage lives in test_cli.py's
    ``test_default_runner_lets_a_caller_exported_bound_win``)."""
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "uvx", GIT_ENV_SHIM)
    _shim(bin_dir, "curl")

    ran = _run(
        tmp_path,
        "--harness",
        "claude-code",
        path=bin_dir,
        home=tmp_path / "home",
        env_overrides={"GIT_HTTP_LOW_SPEED_TIME": "5"},
    )

    assert ran == [
        f"{bin_dir / 'uvx'} {FROM} cheese install --harness claude-code "
        "GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=5"
    ]


def test_installs_uv_first_when_the_host_has_none_and_then_runs_it(tmp_path: Path) -> None:
    """The bare cloud box: curl, git, and node. uv has to arrive before anything else."""
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)
    script = _pinned_to(tmp_path, UV_INSTALLER_BODY)

    ran = _run(tmp_path, "--harness", "codex", path=bin_dir, home=tmp_path / "home", script=script)

    # `uvx` existed nowhere on PATH, so reaching it at all proves the script
    # both installed uv and put its target directory on PATH.
    curl_line, uvx_line = ran
    assert curl_line.startswith(
        f"{bin_dir / 'curl'} -fsSL --proto =https --tlsv1.2 --connect-timeout 10 --max-time 120 -o "
    )
    assert curl_line.endswith(f"https://astral.sh/uv/{_pinned_version()}/install.sh")
    assert uvx_line == f"installed-uvx {FROM} cheese install --harness codex"


def test_an_unpinned_uv_installer_is_refused_before_it_runs(tmp_path: Path) -> None:
    """The one place this script executes code that is not ours.

    A compromised or swapped astral.sh would otherwise run arbitrary code as the
    user, so the download is hashed before `sh` ever sees it.
    """
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)
    tampered = UV_INSTALLER_BODY + '\ntouch "$HOME/pwned"\n'
    # The unmodified script: its pin matches the real installer, not this one.
    completed, _ = _invoke(
        tmp_path,
        "--harness",
        "codex",
        path=bin_dir,
        home=tmp_path / "home",
        installer_body=tampered,
    )

    assert completed.returncode == 1
    assert "refusing to run the uv installer" in completed.stderr
    assert not (tmp_path / "home" / "pwned").exists(), "the installer body must never execute"
    # The run stops on the mismatch rather than limping on to a confusing
    # "uvx: not found" further down.
    assert "uv install failed" in completed.stderr


def test_the_pin_names_a_version_and_a_full_digest() -> None:
    """A hash pinned against the unversioned URL breaks on every uv release.

    Astral serves /uv/install.sh from whatever release is current; only
    /uv/<version>/install.sh is frozen, so the version must reach the URL.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert re.search(r'UV_VERSION="\d+\.\d+\.\d+"', source)
    assert re.search(r'UV_INSTALLER_SHA256="[0-9a-f]{64}"', source)
    assert "https://astral.sh/uv/${UV_VERSION}/install.sh" in source
    assert "https://astral.sh/uv/install.sh" not in source


def test_a_failed_uv_install_stops_the_run_and_names_the_real_failure(tmp_path: Path) -> None:
    """A uv install that leaves no binary must be named, not discovered later.

    Without the check the run continues to `exec uvx` and dies as `uvx: not
    found`, blaming the wrong thing on a host where nothing was installed.
    """
    bin_dir = tmp_path / "bin"
    # A curl that downloads nothing: it writes no file, so verification has
    # nothing to hash and no uv appears.
    _shim(bin_dir, "curl")

    completed, ran = _invoke(tmp_path, "--harness", "codex", path=bin_dir, home=tmp_path / "home")

    assert completed.returncode == 1
    assert "uv install failed" in completed.stderr
    assert len(ran) == 1, "curl must be attempted exactly once"


def test_stdout_carries_only_the_installs_own_output(tmp_path: Path) -> None:
    """`--json` is the documented headless interface, so nothing may precede it.

    The uv installer narrates on stdout. Left there it lands ahead of the JSON
    document and breaks any caller piping the one-liner into a parser — only on
    the bare hosts that need uv installed, which is where it matters most.
    """
    bin_dir = tmp_path / "bin"
    _shim(bin_dir, "curl", UV_INSTALLER_SHIM)
    # The generated uvx echoes a JSON-ish document, standing in for the report.
    completed, _ = _invoke(
        tmp_path,
        "--json",
        path=bin_dir,
        home=tmp_path / "home",
        script=_pinned_to(tmp_path, UV_INSTALLER_BODY),
    )

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
