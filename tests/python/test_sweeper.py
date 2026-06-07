"""Port of `tests/sweeper.test.ts`.

Line-by-line port of the vitest cases. The TS suite uses ``mkdtemp`` +
``afterEach`` cleanup; pytest's ``tmp_path`` is per-test, so we use it
directly (and ``tmp_path_factory`` for the live-target sibling dirs).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from cheese_flow.lib.sweeper import SweepOptions, sweep


def _set_mtime(target: Path, days_ago: float) -> None:
    when = time.time() - days_ago * 24 * 60 * 60
    os.utime(target, (when, when))


def _make_home(tmp_path: Path) -> Path:
    home = tmp_path / "cheese-home"
    (home / "projects").mkdir(parents=True)
    return home


def _create_project(home: Path, slug: str) -> Path:
    project_dir = home / "projects" / slug
    (project_dir / "milknado").mkdir(parents=True)
    (project_dir / "worktrees").mkdir(parents=True)
    (project_dir / "shared").mkdir(parents=True)
    return project_dir


# region: sweep — milknado db retention


def test_reaps_milknado_db_older_than_default_days(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-repo")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("stale-bytes", encoding="utf-8")
    _set_mtime(db, 31)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(db) in [r["path"] for r in report["reaped"]]
    assert not db.exists()


def test_keeps_milknado_db_younger_than_default_days(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-fresh")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("fresh", encoding="utf-8")
    _set_mtime(db, 5)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(db) not in [r["path"] for r in report["reaped"]]
    assert db.is_file()


def test_respects_per_repo_milknado_days_override(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-override")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("x", encoding="utf-8")
    _set_mtime(db, 10)
    (project_dir / "shared" / "retention.toml").write_text("milknadoDays = 7\n", encoding="utf-8")

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(db) in [r["path"] for r in report["reaped"]]


# endregion

# region: sweep — manifests + runs retention


def test_reaps_stale_manifests_keeps_fresh_runs(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-mixed")
    wt_dir = project_dir / "worktrees" / "-Users-paul-mixed"
    (wt_dir / "manifests").mkdir(parents=True)
    (wt_dir / "runs" / "abc").mkdir(parents=True)
    (wt_dir / ".path").write_text(f"{wt_dir}\n", encoding="utf-8")
    _set_mtime(wt_dir / "manifests", 40)
    _set_mtime(wt_dir / "runs" / "abc", 5)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(wt_dir / "manifests") in [r["path"] for r in report["reaped"]]
    assert (wt_dir / "runs" / "abc").is_dir()


def test_reaps_individual_stale_run_dirs(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-runs")
    wt_dir = project_dir / "worktrees" / "-Users-paul-runs"
    stale = wt_dir / "runs" / "stale"
    fresh = wt_dir / "runs" / "fresh"
    stale.mkdir(parents=True)
    fresh.mkdir(parents=True)
    (wt_dir / ".path").write_text(f"{wt_dir}\n", encoding="utf-8")
    _set_mtime(stale, 90)
    _set_mtime(fresh, 1)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    paths = [r["path"] for r in report["reaped"]]
    assert str(stale) in paths
    assert str(fresh) not in paths


# endregion

# region: sweep — whole-worktree reaping


def test_reaps_whole_worktree_only_when_stale_and_path_target_gone(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-dead")
    live_dir = tmp_path_factory.mktemp("cheese-sweep-live-")

    live_slug = "-Users-paul-live"
    dead_slug = "-Users-paul-dead-wt"
    live_wt = project_dir / "worktrees" / live_slug
    dead_wt = project_dir / "worktrees" / dead_slug
    live_wt.mkdir(parents=True)
    dead_wt.mkdir(parents=True)
    (live_wt / ".path").write_text(f"{live_dir}\n", encoding="utf-8")
    (dead_wt / ".path").write_text(
        "/tmp/cheese-this-path-should-not-exist-12345\n", encoding="utf-8"
    )
    # both old enough
    _set_mtime(live_wt, 120)
    _set_mtime(dead_wt, 120)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    reaped = [r["path"] for r in report["reaped"]]
    assert str(dead_wt) in reaped
    assert str(live_wt) not in reaped
    assert not dead_wt.exists()
    assert live_wt.is_dir()


def test_does_not_reap_stale_worktree_if_path_target_exists(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-stale-but-live")
    live_dir = tmp_path_factory.mktemp("cheese-sweep-live2-")
    wt = project_dir / "worktrees" / "-Users-paul-stale"
    wt.mkdir(parents=True)
    (wt / ".path").write_text(f"{live_dir}\n", encoding="utf-8")
    _set_mtime(wt, 120)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(wt) not in [r["path"] for r in report["reaped"]]


# endregion

# region: sweep — never reaps in-repo .cheese/


def test_only_walks_cheese_projects_never_user_repo(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-isolation")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("x", encoding="utf-8")
    _set_mtime(db, 90)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert report["scannedProjects"] == 1
    assert len(report["reaped"]) >= 1
    for entry in report["reaped"]:
        assert entry["path"].startswith(str(home))


# endregion

# region: sweep — debounce via .last-sweep


def test_noop_when_last_sweep_within_24h(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-debounced")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("stale", encoding="utf-8")
    _set_mtime(db, 90)
    last_sweep = home / ".last-sweep"
    last_sweep.write_text("", encoding="utf-8")
    _set_mtime(last_sweep, 0)  # just now

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert report["reaped"] == []
    assert report["scannedProjects"] == 0
    assert db.is_file()


def test_runs_and_touches_last_sweep_when_older_than_24h(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-due")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("stale", encoding="utf-8")
    _set_mtime(db, 90)
    last_sweep = home / ".last-sweep"
    last_sweep.write_text("", encoding="utf-8")
    _set_mtime(last_sweep, 2)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert len(report["reaped"]) >= 1
    after = last_sweep.stat()
    assert (time.time() * 1000) - (after.st_mtime * 1000) < 60_000


def test_force_bypasses_debounce(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-force")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("stale", encoding="utf-8")
    _set_mtime(db, 90)
    last_sweep = home / ".last-sweep"
    last_sweep.write_text("", encoding="utf-8")
    _set_mtime(last_sweep, 0)

    report = sweep(SweepOptions(scope="all", home=str(home), force=True))

    assert len(report["reaped"]) >= 1


# endregion

# region: sweep — dryRun


def test_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-dry")
    db = project_dir / "milknado" / "milknado.db"
    db.write_text("x", encoding="utf-8")
    _set_mtime(db, 90)

    report = sweep(SweepOptions(scope="all", home=str(home), dryRun=True))

    assert str(db) in [r["path"] for r in report["reaped"]]
    assert db.is_file()


# endregion

# region: sweep — sidecar edge cases


def test_treats_empty_path_sidecar_as_dead_target(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-empty-path")
    wt = project_dir / "worktrees" / "-Users-paul-empty"
    wt.mkdir(parents=True)
    (wt / ".path").write_text("   \n", encoding="utf-8")
    _set_mtime(wt, 120)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(wt) in [r["path"] for r in report["reaped"]]


def test_treats_missing_path_sidecar_as_dead_target(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-no-sidecar")
    wt = project_dir / "worktrees" / "-Users-paul-nosidecar"
    wt.mkdir(parents=True)
    _set_mtime(wt, 120)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert str(wt) in [r["path"] for r in report["reaped"]]


def test_ignores_non_directory_entries_under_worktrees_and_runs(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-files")
    wt = project_dir / "worktrees" / "-Users-paul-files"
    (wt / "runs").mkdir(parents=True)
    (wt / ".path").write_text(f"{wt}\n", encoding="utf-8")
    # stray file under worktrees/
    (project_dir / "worktrees" / "stray.txt").write_text("x", encoding="utf-8")
    # stray file under runs/
    (wt / "runs" / "stray.txt").write_text("x", encoding="utf-8")

    report = sweep(SweepOptions(scope="all", home=str(home)))

    reaped = [r["path"] for r in report["reaped"]]
    assert str(project_dir / "worktrees" / "stray.txt") not in reaped
    assert str(wt / "runs" / "stray.txt") not in reaped


def test_returns_duration_and_empty_errors_on_clean_sweep(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _create_project(home, "-Users-paul-clean")

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert report["errors"] == []
    assert isinstance(report["durationMs"], int)
    assert report["durationMs"] >= 0


def test_scope_project_sweeps_only_supplied_project_dir(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    a = _create_project(home, "-Users-paul-scoped-a")
    b = _create_project(home, "-Users-paul-scoped-b")
    db_a = a / "milknado" / "milknado.db"
    db_b = b / "milknado" / "milknado.db"
    db_a.write_text("x", encoding="utf-8")
    db_b.write_text("x", encoding="utf-8")
    _set_mtime(db_a, 90)
    _set_mtime(db_b, 90)

    report = sweep(SweepOptions(scope="project", home=str(home), projectDir=str(a)))

    assert report["scannedProjects"] == 1
    reaped = [r["path"] for r in report["reaped"]]
    assert str(db_a) in reaped
    assert str(db_b) not in reaped


def test_returns_zero_scanned_when_projects_dir_missing(tmp_path: Path) -> None:
    home = tmp_path / "cheese-home-empty"
    home.mkdir()

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert report["scannedProjects"] == 0
    assert report["reaped"] == []


def test_handles_project_dir_with_no_worktrees(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = home / "projects" / "-Users-paul-no-wts"
    (project_dir / "milknado").mkdir(parents=True)
    (project_dir / "shared").mkdir(parents=True)
    # intentionally NO worktrees/ directory

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert report["scannedProjects"] == 1
    assert report["errors"] == []


def test_skips_reap_target_with_failing_stat_broken_symlink(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-broken-orphan")
    broken = project_dir / "worktrees" / ".reap-12345-broken-symlink"
    os.symlink("/nonexistent/path/that/does/not/exist", broken)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    # Either reap (succeeded as symlink unlink) or skipped because stat failed.
    # We assert no errors are surfaced, and the orphan didn't crash the sweep.
    assert report["errors"] == []


def test_records_rename_failure_as_non_fatal_error(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-readonly-parent")
    wt = project_dir / "worktrees" / ".reap-99999-orphan"
    wt.mkdir(parents=True)
    worktrees_parent = wt.parent
    # make worktrees/ read-only AFTER creating the orphan, so scandir succeeds
    # but rename inside it fails with EACCES.
    os.chmod(worktrees_parent, 0o500)
    try:
        report = sweep(SweepOptions(scope="all", home=str(home)))
        assert len(report["errors"]) >= 1
        assert report["errors"][0]["path"] == str(wt)
    finally:
        os.chmod(worktrees_parent, 0o755)


# endregion

# region: sweep — atomicity: orphan .reap-* dirs are cleaned


def test_removes_leftover_reap_siblings_on_next_run(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    project_dir = _create_project(home, "-Users-paul-orphan")
    wt_dir = project_dir / "worktrees" / "-Users-paul-orphan"
    wt_dir.mkdir(parents=True)
    (wt_dir / ".path").write_text(f"{wt_dir}\n", encoding="utf-8")
    orphan = project_dir / "worktrees" / ".reap-12345-stale-runs"
    orphan.mkdir(parents=True)

    report = sweep(SweepOptions(scope="all", home=str(home)))

    assert not orphan.exists()
    assert str(orphan) in [r["path"] for r in report["reaped"]]


# endregion
