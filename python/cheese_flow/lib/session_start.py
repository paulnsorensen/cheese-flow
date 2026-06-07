"""Port of `src/lib/session-start.ts` — update checks + housekeeping.

Mirrors the TS surface: ``check_for_update``, ``should_check_update``,
``record_nudged_version``, ``run_session_start``. The TS module imports
``ensureCheeseHome`` from ``./cheese-home.ts``; US-012 hasn't ported
``cheese-home.ts`` yet, so this file inlines the minimal surface
(``_ensure_cheese_home``). When US-012 lands, the inlined helper moves there.

The TS abort/timeout protocol on ``fetch`` translates to ``asyncio.wait_for``:
the abort behaviour under test ("returns null when fetch times out") is
preserved by cancelling the awaited fetch when the deadline elapses.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cheese_flow.lib.sweeper import SweepOptions, SweepReport, sweep

DEFAULT_REGISTRY_URL = "https://registry.npmjs.org/cheese-flow/latest"
DEBOUNCE_MS = 24 * 60 * 60 * 1000
SWEEP_FLOOR_MS = 1000
UPDATE_FLOOR_MS = 500
FETCH_TIMEOUT_MS = 1000


@dataclass
class UpdateNudge:
    version: str
    current: str
    message: str


@dataclass
class UpdateCheckResult:
    behind: bool
    latestVersion: str | None


FetchCallable = Callable[..., Awaitable[Any]]


@dataclass
class CheckForUpdateOptions:
    currentVersion: str
    timeoutMs: int | None = None
    fetch: FetchCallable | None = None
    registryUrl: str | None = None


class _DefaultResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.ok = 200 <= status < 300
        self._body = body

    async def json(self) -> Any:
        return json.loads(self._body.decode("utf-8"))


async def _default_fetch(url: str) -> _DefaultResponse:
    def _do() -> _DefaultResponse:
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            return _DefaultResponse(resp.status, resp.read())

    return await asyncio.to_thread(_do)


async def check_for_update(
    opts: CheckForUpdateOptions,
) -> UpdateCheckResult | None:
    fetch_fn = opts.fetch if opts.fetch is not None else _default_fetch
    timeout_ms = opts.timeoutMs if opts.timeoutMs is not None else FETCH_TIMEOUT_MS
    url = opts.registryUrl if opts.registryUrl is not None else DEFAULT_REGISTRY_URL
    try:
        response = await asyncio.wait_for(fetch_fn(url), timeout=timeout_ms / 1000)
        if not getattr(response, "ok", False):
            return None
        body = await response.json()
        if not isinstance(body, dict):
            return None
        version = body.get("version")
        latest = version if isinstance(version, str) and len(version) > 0 else None
        if latest is None:
            return None
        return UpdateCheckResult(
            behind=latest != opts.currentVersion,
            latestVersion=latest,
        )
    except Exception:
        return None


def _read_update_check(home: str) -> dict[str, Any] | None:
    try:
        body = Path(home, ".update-check").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    checked_at = parsed.get("checked_at")
    latest_version = parsed.get("latest_version")
    nudged_for_version = parsed.get("nudged_for_version")
    return {
        "checked_at": checked_at if isinstance(checked_at, str) else "",
        "latest_version": latest_version if isinstance(latest_version, str) else None,
        "nudged_for_version": (nudged_for_version if isinstance(nudged_for_version, str) else None),
    }


def _write_update_check(home: str, record: dict[str, Any]) -> None:
    Path(home, ".update-check").write_text(json.dumps(record), encoding="utf-8")


def _iso(dt: datetime) -> str:
    """Mirror JS ``Date.toISOString()`` — 3-digit ms, trailing ``Z``."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt_utc = dt.astimezone(UTC)
    ms = dt_utc.microsecond // 1000
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}Z"


def should_check_update(home: str, now: datetime) -> bool:
    try:
        body = Path(home, ".update-check").read_text(encoding="utf-8")
    except OSError:
        return True
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return True
    if not isinstance(parsed, dict):
        return True
    checked_at = parsed.get("checked_at")
    if not isinstance(checked_at, str):
        return True
    try:
        last = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    last_ms = int(last.timestamp() * 1000)
    now_ms = int(_aware(now).timestamp() * 1000)
    return now_ms - last_ms >= DEBOUNCE_MS


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def record_nudged_version(home: str, version: str, now: datetime) -> None:
    _write_update_check(
        home,
        {
            "checked_at": _iso(now),
            "latest_version": version,
            "nudged_for_version": version,
        },
    )


def _prior_nudged_version(home: str) -> str | None:
    record = _read_update_check(home)
    return record["nudged_for_version"] if record else None


def _record_check(
    home: str,
    latest_version: str | None,
    nudged_version: str | None,
    now: datetime,
) -> None:
    _write_update_check(
        home,
        {
            "checked_at": _iso(now),
            "latest_version": latest_version,
            "nudged_for_version": nudged_version,
        },
    )


@dataclass
class RunSessionStartOptions:
    cwd: str
    maxTimeMs: int
    currentVersion: str
    home: str | None = None
    now: datetime | None = None
    fetch: FetchCallable | None = None
    log: Callable[[str], None] | None = None
    quiet: bool = False


@dataclass
class SessionStartResult:
    ok: bool = True
    sweptReport: SweepReport | None = None
    updateNudge: UpdateNudge | None = None


def _default_log(message: str) -> None:
    sys.stdout.write(f"{message}\n")


async def run_session_start(opts: RunSessionStartOptions) -> SessionStartResult:
    now = opts.now if opts.now is not None else datetime.now(UTC)
    log = opts.log if opts.log is not None else _default_log
    deadline = time.monotonic() + opts.maxTimeMs / 1000.0

    def remaining_ms() -> int:
        return int((deadline - time.monotonic()) * 1000)

    paths = _ensure_cheese_home(opts.cwd, home=opts.home)

    result = SessionStartResult(ok=True)

    if remaining_ms() > SWEEP_FLOOR_MS:
        report = sweep(
            SweepOptions(
                scope="all",
                home=paths.root,
                now=int(_aware(now).timestamp() * 1000),
            )
        )
        if not opts.quiet and len(report["reaped"]) > 0:
            log(f"cheese: swept {len(report['reaped'])} stale entries")
        result.sweptReport = report

    if remaining_ms() > UPDATE_FLOOR_MS and should_check_update(paths.root, now):
        update_opts = CheckForUpdateOptions(
            currentVersion=opts.currentVersion,
            timeoutMs=FETCH_TIMEOUT_MS,
        )
        if opts.fetch is not None:
            update_opts.fetch = opts.fetch
        update = await check_for_update(update_opts)
        if update is not None:
            prior = _prior_nudged_version(paths.root)
            if update.behind and update.latestVersion is not None and update.latestVersion != prior:
                nudge = UpdateNudge(
                    version=update.latestVersion,
                    current=opts.currentVersion,
                    message=(
                        f"cheese-flow {update.latestVersion} is available "
                        f"(current: {opts.currentVersion})"
                    ),
                )
                if not opts.quiet:
                    log(nudge.message)
                _record_check(paths.root, update.latestVersion, update.latestVersion, now)
                result.updateNudge = nudge
            else:
                _record_check(paths.root, update.latestVersion, prior, now)

    return result


# ---------- inlined cheese-home helper (US-012 will absorb this) ----------


@dataclass
class _CheeseHomePaths:
    root: str
    projectDir: str
    milknadoDb: str
    worktreeDir: str
    manifestsDir: str
    runsDir: str
    sharedDir: str


def _path_slug(abs_path: str) -> str:
    return abs_path.replace("/", "-")


def _discover_canonical_repo(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise RuntimeError(
            f"discoverCanonicalRepo: {cwd} is not inside a git repo: {error}"
        ) from error
    out = result.stdout
    first_line = out.split("\n", 1)[0] if out else ""
    if not first_line.startswith("worktree "):
        raise RuntimeError(
            f"discoverCanonicalRepo: {cwd} is not inside a git worktree (no 'worktree' line)"
        )
    return str(Path(first_line[len("worktree ") :]).resolve())


def _ensure_cheese_home(cwd: str, *, home: str | None = None) -> _CheeseHomePaths:
    root = home if home is not None else str(Path.home() / ".cheese")
    canonical_repo = _discover_canonical_repo(cwd)
    repo_slug = _path_slug(canonical_repo)
    worktree_path = str(Path(cwd).resolve())
    wt_slug = _path_slug(worktree_path)
    project_dir = os.path.join(root, "projects", repo_slug)
    worktree_dir = os.path.join(project_dir, "worktrees", wt_slug)
    paths = _CheeseHomePaths(
        root=root,
        projectDir=project_dir,
        milknadoDb=os.path.join(project_dir, "milknado", "milknado.db"),
        worktreeDir=worktree_dir,
        manifestsDir=os.path.join(worktree_dir, "manifests"),
        runsDir=os.path.join(worktree_dir, "runs"),
        sharedDir=os.path.join(project_dir, "shared"),
    )
    os.makedirs(os.path.dirname(paths.milknadoDb), exist_ok=True)
    os.makedirs(paths.manifestsDir, exist_ok=True)
    os.makedirs(paths.runsDir, exist_ok=True)
    os.makedirs(paths.sharedDir, exist_ok=True)
    Path(worktree_dir, ".path").write_text(f"{worktree_path}\n", encoding="utf-8")
    return paths
