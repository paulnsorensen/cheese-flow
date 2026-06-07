"""Port of `src/lib/sweeper.ts` — stale-file cleanup logic for ~/.cheese.

Mirrors the TS surface: ``sweep`` returns a ``SweepReport`` describing reaped
entries and any non-fatal errors. Atomic deletion via rename-into-orphan-then-rm,
24h debounce via ``.last-sweep`` mtime, per-repo retention overrides via
``shared/retention.toml``.

The TS module imports ``readRetentionConfig`` and ``RetentionConfig`` from
``./cheese-home.ts``. US-012 hasn't ported ``cheese-home.ts`` yet, so this file
inlines the minimal retention-config surface. When US-012 lands, the inlined
helpers can move there.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

DEBOUNCE_MS = 24 * 60 * 60 * 1000
ORPHAN_PREFIX = ".reap-"
DEFAULT_RETENTION_DAYS = 30
_RETENTION_NUMERIC_KEYS: frozenset[str] = frozenset(
    {
        "defaultDays",
        "milknadoDays",
        "manifestsDays",
        "runsDays",
        "worktreeDays",
    }
)


@dataclass
class RetentionConfig:
    defaultDays: int = DEFAULT_RETENTION_DAYS
    milknadoDays: int | None = None
    manifestsDays: int | None = None
    runsDays: int | None = None
    worktreeDays: int | None = None


class ReapEntry(TypedDict):
    path: str
    reason: str
    bytes: int


class SweepError(TypedDict):
    path: str
    error: str


class SweepReport(TypedDict):
    scannedProjects: int
    reaped: list[ReapEntry]
    errors: list[SweepError]
    durationMs: int


@dataclass
class SweepOptions:
    scope: Literal["all", "project"]
    home: str
    projectDir: str | None = None
    now: float | None = None  # epoch ms; mirrors TS Date.getTime()
    dryRun: bool = False
    force: bool = False


def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_now_ms(now: float | None) -> int:
    if now is None:
        return _now_ms()
    return int(now)


def _read_retention_config(project_dir: str) -> RetentionConfig:
    toml_path = Path(project_dir) / "shared" / "retention.toml"
    try:
        body = toml_path.read_text(encoding="utf-8")
    except OSError:
        return RetentionConfig()
    return _parse_retention_toml(body)


def _strip_comment(line: str) -> str:
    hash_idx = line.find("#")
    return line if hash_idx < 0 else line[:hash_idx]


def _parse_retention_toml(body: str) -> RetentionConfig:
    config: dict[str, int] = {"defaultDays": DEFAULT_RETENTION_DAYS}
    for raw_line in body.splitlines():
        line = _strip_comment(raw_line).strip()
        if line == "" or line.startswith("["):
            continue
        eq = line.find("=")
        if eq < 0:
            continue
        key = line[:eq].strip()
        value = line[eq + 1 :].strip()
        if key not in _RETENTION_NUMERIC_KEYS:
            continue
        try:
            parsed = int(value, 10)
        except ValueError:
            continue
        config[key] = parsed
    return RetentionConfig(
        defaultDays=config.get("defaultDays", DEFAULT_RETENTION_DAYS),
        milknadoDays=config.get("milknadoDays"),
        manifestsDays=config.get("manifestsDays"),
        runsDays=config.get("runsDays"),
        worktreeDays=config.get("worktreeDays"),
    )


def sweep(opts: SweepOptions) -> SweepReport:
    start = _now_ms()
    now_ms = _to_now_ms(opts.now)
    last_sweep = os.path.join(opts.home, ".last-sweep")

    if not opts.force and _is_debounced(last_sweep, now_ms):
        return SweepReport(
            scannedProjects=0,
            reaped=[],
            errors=[],
            durationMs=_now_ms() - start,
        )

    project_dirs = _collect_project_dirs(opts)
    reaped: list[ReapEntry] = []
    errors: list[SweepError] = []
    for project_dir in project_dirs:
        config = _read_retention_config(project_dir)
        _sweep_project(project_dir, config, now_ms, opts.dryRun, reaped, errors)
    if not opts.dryRun:
        _touch_file(last_sweep, now_ms)
    return SweepReport(
        scannedProjects=len(project_dirs),
        reaped=reaped,
        errors=errors,
        durationMs=_now_ms() - start,
    )


def _is_debounced(last_sweep: str, now_ms: int) -> bool:
    try:
        info = os.stat(last_sweep)
    except OSError:
        return False
    return now_ms - int(info.st_mtime * 1000) < DEBOUNCE_MS


def _collect_project_dirs(opts: SweepOptions) -> list[str]:
    if opts.scope == "project" and opts.projectDir:
        return [opts.projectDir]
    projects_root = os.path.join(opts.home, "projects")
    try:
        entries = list(os.scandir(projects_root))
    except OSError:
        return []
    return [entry.path for entry in entries if entry.is_dir()]


def _sweep_project(
    project_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    _reap_milknado(project_dir, config, now_ms, dry_run, reaped, errors)
    _reap_worktrees(project_dir, config, now_ms, dry_run, reaped, errors)


def _reap_milknado(
    project_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    db = os.path.join(project_dir, "milknado", "milknado.db")
    days = config.milknadoDays if config.milknadoDays is not None else config.defaultDays
    if _is_older_than(db, now_ms, days):
        _reap(db, f"milknado.db older than {days}d", dry_run, reaped, errors)


def _reap_worktrees(
    project_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    wt_root = os.path.join(project_dir, "worktrees")
    try:
        entries = list(os.scandir(wt_root))
    except OSError:
        return
    for entry in entries:
        child = os.path.join(wt_root, entry.name)
        if entry.name.startswith(ORPHAN_PREFIX):
            _reap(child, "orphaned reap-tmp", dry_run, reaped, errors)
            continue
        if not entry.is_dir():
            continue
        _sweep_worktree(child, config, now_ms, dry_run, reaped, errors)


def _sweep_worktree(
    worktree_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    wt_days = config.worktreeDays if config.worktreeDays is not None else config.defaultDays
    if _is_older_than(worktree_dir, now_ms, wt_days) and not _sidecar_target_exists(worktree_dir):
        _reap(
            worktree_dir,
            f"worktree dir older than {wt_days}d AND .path target gone",
            dry_run,
            reaped,
            errors,
        )
        return
    _reap_manifests(worktree_dir, config, now_ms, dry_run, reaped, errors)
    _reap_runs(worktree_dir, config, now_ms, dry_run, reaped, errors)


def _reap_manifests(
    worktree_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    manifests = os.path.join(worktree_dir, "manifests")
    days = config.manifestsDays if config.manifestsDays is not None else config.defaultDays
    if _is_older_than(manifests, now_ms, days):
        _reap(manifests, f"manifests older than {days}d", dry_run, reaped, errors)


def _reap_runs(
    worktree_dir: str,
    config: RetentionConfig,
    now_ms: int,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    runs = os.path.join(worktree_dir, "runs")
    days = config.runsDays if config.runsDays is not None else config.defaultDays
    try:
        entries = list(os.scandir(runs))
    except OSError:
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        run_dir = os.path.join(runs, entry.name)
        if _is_older_than(run_dir, now_ms, days):
            _reap(run_dir, f"run dir older than {days}d", dry_run, reaped, errors)


def _sidecar_target_exists(worktree_dir: str) -> bool:
    sidecar = os.path.join(worktree_dir, ".path")
    try:
        body = Path(sidecar).read_text(encoding="utf-8")
    except OSError:
        return False
    target = body.strip()
    if len(target) == 0:
        return False
    try:
        os.stat(target)
        return True
    except OSError:
        return False


def _is_older_than(target: str, now_ms: int, days: int) -> bool:
    try:
        info = os.stat(target)
    except OSError:
        return False
    age_ms = now_ms - int(info.st_mtime * 1000)
    return age_ms > days * 24 * 60 * 60 * 1000


def _reap(
    target: str,
    reason: str,
    dry_run: bool,
    reaped: list[ReapEntry],
    errors: list[SweepError],
) -> None:
    try:
        info = os.stat(target)
    except OSError:
        return
    bytes_ = 0 if os.path.isdir(target) else info.st_size
    reaped.append(ReapEntry(path=target, reason=reason, bytes=bytes_))
    if dry_run:
        return
    try:
        tmp = f"{os.path.dirname(target)}/{ORPHAN_PREFIX}{_now_ms()}-{os.path.basename(target)}"
        os.rename(target, tmp)
        if os.path.isdir(tmp) and not os.path.islink(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    except OSError as error:
        errors.append(
            SweepError(
                path=target,
                error=str(error) if str(error) else type(error).__name__,
            )
        )


def _touch_file(target: str, now_ms: int) -> None:
    try:
        Path(target).touch(exist_ok=True)
        ts = now_ms / 1000.0
        os.utime(target, (ts, ts))
    except OSError:
        # best effort
        pass
