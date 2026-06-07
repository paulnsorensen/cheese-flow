"""Port of `tests/session-start.test.ts`.

Line-by-line port of the vitest cases. The TS suite uses ``mkdtemp`` +
``afterEach`` cleanup; pytest's ``tmp_path`` is per-test, so we use it
directly. The TS ``vi.fn()`` mocks become ``unittest.mock.AsyncMock`` /
``MagicMock``; the JS ``fetch`` Response shape is mirrored by a tiny
``_MockResponse`` helper. The codebase does not depend on ``pytest-asyncio``,
so async cases drive the coroutine through ``asyncio.run`` to match the
existing harness in ``test_installer.py`` and ``test_harness_detection.py``.

The final TS case (``registers the session-start subcommand and prints help
text``) shells out to ``npx tsx src/index.ts session-start --help``. The Python
``cheese`` Typer app does not exist yet (arrives in US-015), so that case is
deferred to ``test_cli.py`` in US-015.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cheese_flow.lib.session_start import (
    CheckForUpdateOptions,
    RunSessionStartOptions,
    _iso,
    check_for_update,
    record_nudged_version,
    run_session_start,
    should_check_update,
)


class _MockResponse:
    """Mirrors the JS ``Response`` shape used by ``checkForUpdate``."""

    def __init__(self, *, ok: bool, body: Any) -> None:
        self.ok = ok
        self._body = body

    async def json(self) -> Any:
        return self._body


def _make_home(tmp_path: Path) -> Path:
    home = tmp_path / f"session-start-home-{time.time_ns()}"
    home.mkdir(parents=True)
    return home


def _make_repo(tmp_path: Path) -> Path:
    cwd = tmp_path / f"session-start-repo-{time.time_ns()}"
    cwd.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(cwd)],
        check=True,
    )
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    subprocess.run(
        ["git", "-C", str(cwd), "commit", "--allow-empty", "-m", "init", "--quiet"],
        env=env,
        check=True,
    )
    return cwd


# region: check_for_update


def test_check_for_update_returns_behind_true_when_registry_newer() -> None:
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "9.9.9"}))

    result = asyncio.run(
        check_for_update(
            CheckForUpdateOptions(currentVersion="0.1.0", timeoutMs=1000, fetch=fetch_fn)
        )
    )

    assert result is not None
    assert result.behind is True
    assert result.latestVersion == "9.9.9"


def test_check_for_update_returns_behind_false_when_current_matches() -> None:
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "0.1.0"}))

    result = asyncio.run(
        check_for_update(
            CheckForUpdateOptions(currentVersion="0.1.0", timeoutMs=1000, fetch=fetch_fn)
        )
    )

    assert result is not None
    assert result.behind is False


def test_check_for_update_returns_null_on_timeout() -> None:
    """TS test uses AbortController; Python uses asyncio.wait_for cancellation."""

    async def slow(_url: str) -> _MockResponse:
        await asyncio.Event().wait()  # never resolves; wait_for cancels it
        return _MockResponse(ok=True, body={})

    result = asyncio.run(
        check_for_update(CheckForUpdateOptions(currentVersion="0.1.0", timeoutMs=5, fetch=slow))
    )

    assert result is None


def test_check_for_update_returns_null_on_non_ok_response() -> None:
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=False, body={}))

    result = asyncio.run(
        check_for_update(
            CheckForUpdateOptions(currentVersion="0.1.0", timeoutMs=1000, fetch=fetch_fn)
        )
    )

    assert result is None


def test_check_for_update_returns_null_when_no_version_field() -> None:
    fetch_fn = AsyncMock(
        return_value=_MockResponse(ok=True, body={"description": "no version here"})
    )

    result = asyncio.run(
        check_for_update(
            CheckForUpdateOptions(currentVersion="0.1.0", timeoutMs=1000, fetch=fetch_fn)
        )
    )

    assert result is None


# region: should_check_update / record_nudged_version


def test_should_check_update_returns_true_on_first_run(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    assert should_check_update(str(home), datetime.now(UTC)) is True


def test_should_check_update_returns_false_within_24h(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    now = datetime.now(UTC)
    recent = now - timedelta(hours=1)
    (home / ".update-check").write_text(
        json.dumps(
            {
                "checked_at": recent.isoformat().replace("+00:00", "Z"),
                "latest_version": "0.1.0",
                "nudged_for_version": None,
            }
        ),
        encoding="utf-8",
    )

    assert should_check_update(str(home), now) is False


def test_should_check_update_returns_true_after_24h(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    now = datetime.now(UTC)
    stale = now - timedelta(hours=25)
    (home / ".update-check").write_text(
        json.dumps(
            {
                "checked_at": stale.isoformat().replace("+00:00", "Z"),
                "latest_version": "0.1.0",
                "nudged_for_version": None,
            }
        ),
        encoding="utf-8",
    )

    assert should_check_update(str(home), now) is True


def test_record_nudged_version_suppresses_repeats(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    now = datetime.now(UTC)

    asyncio.run(record_nudged_version(str(home), "1.2.3", now))

    data = json.loads((home / ".update-check").read_text(encoding="utf-8"))
    assert data["nudged_for_version"] == "1.2.3"
    assert data["latest_version"] == "1.2.3"
    # Mirrors `expect(data.checked_at).toBe(now.toISOString())` — the stored
    # timestamp must round-trip through our JS-shape ISO formatter.
    assert data["checked_at"] == _iso(now)


def test_should_check_update_returns_true_on_malformed_json(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    (home / ".update-check").write_text("not-json{{{", encoding="utf-8")

    assert should_check_update(str(home), datetime.now(UTC)) is True


def test_should_check_update_returns_true_when_checked_at_non_string(
    tmp_path: Path,
) -> None:
    home = _make_home(tmp_path)
    (home / ".update-check").write_text(json.dumps({"checked_at": 12345}), encoding="utf-8")

    assert should_check_update(str(home), datetime.now(UTC)) is True


def test_should_check_update_returns_true_when_checked_at_unparseable(
    tmp_path: Path,
) -> None:
    home = _make_home(tmp_path)
    (home / ".update-check").write_text(json.dumps({"checked_at": "not-a-date"}), encoding="utf-8")

    assert should_check_update(str(home), datetime.now(UTC)) is True


# region: run_session_start — budget + idempotency


def test_run_session_start_returns_ok_and_creates_home_tree(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                log=lambda _msg: None,
            )
        )
    )

    assert result.ok is True
    assert (home / "projects").is_dir()


def test_run_session_start_skips_phases_below_budget(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    fetch_fn = AsyncMock()

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=1,  # below sweep + update floors
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=lambda _msg: None,
            )
        )
    )

    assert result.ok is True
    assert result.sweptReport is None
    assert result.updateNudge is None
    fetch_fn.assert_not_called()


def test_run_session_start_logs_reap_summary_when_non_quiet(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    # Pre-create a stale milknado db inside cheese-home so the sweep finds it.
    projects_dir = home / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    real_cwd = str(Path(cwd).resolve())
    slug = real_cwd.replace("/", "-")
    milknado_dir = projects_dir / slug / "milknado"
    milknado_dir.mkdir(parents=True, exist_ok=True)
    db = milknado_dir / "milknado.db"
    db.write_text("stale", encoding="utf-8")
    ninety_days_ago = time.time() - 90 * 24 * 60 * 60
    os.utime(db, (ninety_days_ago, ninety_days_ago))

    log = MagicMock()
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "0.1.0"}))

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=log,
            )
        )
    )

    assert result.sweptReport is not None
    assert len(result.sweptReport["reaped"]) >= 1
    swept_logs = [c for c in log.call_args_list if "swept" in str(c.args[0])]
    assert len(swept_logs) >= 1


def test_run_session_start_suppresses_log_when_quiet(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    log = MagicMock()
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "9.9.9"}))

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=log,
                quiet=True,
            )
        )
    )

    assert result.updateNudge is not None
    assert result.updateNudge.version == "9.9.9"
    nudge_logs = [c for c in log.call_args_list if "9.9.9" in str(c.args[0])]
    assert nudge_logs == []


def test_run_session_start_records_check_when_no_nudge(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "0.1.0"}))

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=lambda _msg: None,
            )
        )
    )

    assert result.updateNudge is None
    data = json.loads((home / ".update-check").read_text(encoding="utf-8"))
    assert data["latest_version"] == "0.1.0"
    assert isinstance(data["checked_at"], str)


def test_run_session_start_handles_non_string_nudged_for_version(
    tmp_path: Path,
) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    stale = (datetime.now(UTC) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    (home / ".update-check").write_text(
        json.dumps(
            {
                "checked_at": stale,
                "latest_version": 12345,  # wrong type, must be ignored
                "nudged_for_version": False,  # wrong type, treated as null
            }
        ),
        encoding="utf-8",
    )
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "9.9.9"}))

    result = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=lambda _msg: None,
            )
        )
    )

    assert result.updateNudge is not None
    assert result.updateNudge.version == "9.9.9"


def test_run_session_start_suppresses_repeat_nudges(tmp_path: Path) -> None:
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    log = MagicMock()
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "9.9.9"}))

    first = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=log,
            )
        )
    )
    assert first.updateNudge is not None
    assert first.updateNudge.version == "9.9.9"
    initial_nudge_logs = [c for c in log.call_args_list if "9.9.9" in str(c.args[0])]
    assert len(initial_nudge_logs) >= 1

    log.reset_mock()
    second = asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC) + timedelta(hours=25),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
                log=log,
            )
        )
    )

    assert second.updateNudge is None
    repeat_nudge_logs = [c for c in log.call_args_list if "9.9.9" in str(c.args[0])]
    assert len(repeat_nudge_logs) == 0


# region: session-start CLI


def test_run_session_start_default_log_writes_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mirrors the TS case that monkey-patches ``process.stdout.write``."""
    cwd = _make_repo(tmp_path)
    home = _make_home(tmp_path)
    projects_dir = home / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    real_cwd = str(Path(cwd).resolve())
    slug = real_cwd.replace("/", "-")
    milknado_dir = projects_dir / slug / "milknado"
    milknado_dir.mkdir(parents=True, exist_ok=True)
    db = milknado_dir / "milknado.db"
    db.write_text("stale", encoding="utf-8")
    ninety_days_ago = time.time() - 90 * 24 * 60 * 60
    os.utime(db, (ninety_days_ago, ninety_days_ago))
    fetch_fn = AsyncMock(return_value=_MockResponse(ok=True, body={"version": "0.1.0"}))

    asyncio.run(
        run_session_start(
            RunSessionStartOptions(
                cwd=str(cwd),
                home=str(home),
                now=datetime.now(UTC),
                maxTimeMs=5000,
                currentVersion="0.1.0",
                fetch=fetch_fn,
            )
        )
    )

    captured = capsys.readouterr()
    assert "swept" in captured.out


@pytest.mark.skip(
    reason="The `cheese session-start --help` Typer subcommand arrives in US-015; "
    "the help-text registration test moves to test_cli.py at that point."
)
def test_session_start_subcommand_prints_help_text() -> None:  # pragma: no cover
    """Deferred to US-015 — Typer CLI does not exist yet."""
