"""Pure-function tests for tools.git_diagnose core functions. Subprocess paths mocked."""

from __future__ import annotations

import pytest
from tools import git_diagnose as gd

# ─── repo-wide commands ──────────────────────────────────────────────────────


class TestHotspots:
    def test_counts_and_ranks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "src/a.ts\nsrc/a.ts\nsrc/b.ts\nsrc/a.ts\nsrc/c.ts\n"

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.hotspots(since="2.years.ago", limit=2)
        assert result == [
            {"file": "src/a.ts", "changes": 3},
            {"file": "src/b.ts", "changes": 1},
        ]
        assert captured["args"] == ["log", "--since=2.years.ago", "--format=", "--name-only"]

    def test_ignores_blank_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "\n\nsrc/a.ts\n\n")
        assert gd.hotspots() == [{"file": "src/a.ts", "changes": 1}]

    def test_empty_history_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd.hotspots() == []

    def test_default_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return ""

        monkeypatch.setattr(gd, "_run_git", fake)
        gd.hotspots()
        assert captured["args"] == ["log", "--since=1.year.ago", "--format=", "--name-only"]


class TestBusFactor:
    def test_parses_shortlog_and_ranks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "   60\tAlice\n   30\tBob\n   10\tCarol\n"

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.bus_factor(limit=2)
        assert result == [
            {"author": "Alice", "commits": 60, "percent": 60.0},
            {"author": "Bob", "commits": 30, "percent": 30.0},
        ]
        assert captured["args"] == ["shortlog", "-sn", "--no-merges", "--all"]

    def test_skips_malformed_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "garbage\n   5\tAlice\n")
        result = gd.bus_factor()
        assert result == [{"author": "Alice", "commits": 5, "percent": 100.0}]

    def test_empty_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd.bus_factor() == []


class TestBugClusters:
    def test_counts_bug_touches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "src/a.ts\nsrc/a.ts\nsrc/b.ts\n"

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.bug_clusters(limit=5)
        assert result == [
            {"file": "src/a.ts", "bug_changes": 2},
            {"file": "src/b.ts", "bug_changes": 1},
        ]
        assert captured["args"] == [
            "log",
            "-i",
            "-E",
            "--grep=(^|[^[:alnum:]_])(fix(ed|es|ing)?|bug(s)?|broken)([^[:alnum:]_]|$)",
            "--format=",
            "--name-only",
        ]

    def test_empty_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd.bug_clusters() == []


class TestVelocity:
    def test_groups_and_sorts_by_month(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "2025-03\n2025-01\n2025-03\n2025-02\n2025-01\n"

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.velocity()
        assert result == [
            {"month": "2025-01", "commits": 2},
            {"month": "2025-02", "commits": 1},
            {"month": "2025-03", "commits": 2},
        ]
        assert captured["args"] == ["log", "--format=%ad", "--date=format:%Y-%m"]

    def test_empty_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd.velocity() == []


class TestFirefighting:
    def test_matches_firefight_keywords_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return (
                "abc1234 feat: normal change\n"
                'def5678 Revert "bad commit"\n'
                "fed4321 hotfix: urgent\n"
                "999aaaa EMERGENCY rollback of deploy\n"
                "111bbbb chore: covertly refactor\n"
            )

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.firefighting(since="6.months.ago")
        assert result == [
            {"sha": "def5678", "subject": 'Revert "bad commit"'},
            {"sha": "fed4321", "subject": "hotfix: urgent"},
            {"sha": "999aaaa", "subject": "EMERGENCY rollback of deploy"},
        ]
        assert captured["args"] == ["log", "--oneline", "--since=6.months.ago"]

    def test_no_matches_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "abc1234 feat: x\n")
        assert gd.firefighting() == []


# ─── per-file risk ───────────────────────────────────────────────────────────


class TestHumanizeStaleness:
    def test_untracked_when_none(self) -> None:
        assert gd._humanize_staleness(None) == "untracked"

    def test_today_when_zero(self) -> None:
        assert gd._humanize_staleness(0) == "today"

    def test_singular_day(self) -> None:
        assert gd._humanize_staleness(1) == "1 day ago"

    @pytest.mark.parametrize("days,expected", [(2, "2 days ago"), (29, "29 days ago")])
    def test_plural_days_under_month(self, days: int, expected: str) -> None:
        assert gd._humanize_staleness(days) == expected

    @pytest.mark.parametrize(
        "days,expected",
        [(30, "1 month ago"), (60, "2 months ago"), (200, "7 months ago")],
    )
    def test_months(self, days: int, expected: str) -> None:
        assert gd._humanize_staleness(days) == expected

    @pytest.mark.parametrize(
        "days,expected", [(365, "1 year ago"), (730, "2 years ago"), (1825, "5 years ago")]
    )
    def test_years(self, days: int, expected: str) -> None:
        assert gd._humanize_staleness(days) == expected


class TestAuthorsAndChanges90d:
    def test_counts_distinct_and_total(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "alice@x\nbob@x\nalice@x\n"

        monkeypatch.setattr(gd, "_run_git", fake)
        authors, changes = gd._authors_and_changes_90d("foo.py")
        assert authors == 2
        assert changes == 3
        assert captured["args"] == [
            "log",
            "--since=90.days.ago",
            "--format=%ae",
            "--",
            "foo.py",
        ]

    def test_zero_when_no_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd._authors_and_changes_90d("foo.py") == (0, 0)


class TestRevertCount:
    def test_counts_revert_subjects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        log = 'feat: x\nRevert "bad"\nRevert "another"\nfix: y\n'
        monkeypatch.setattr(gd, "_run_git", lambda args: log)
        assert gd._revert_count("foo.py") == 2

    def test_zero_when_no_reverts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "feat: x\nfix: y\n")
        assert gd._revert_count("foo.py") == 0

    def test_does_not_match_substring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # "covert" contains "vert" but does not start with "Revert"
        monkeypatch.setattr(gd, "_run_git", lambda args: "covert refactor\n")
        assert gd._revert_count("foo.py") == 0


class TestLastChangeDays:
    def test_computes_days_from_unix_ts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "1700000000\n")
        days = gd._last_change_days("foo.py", now_ts=1700000000 + 5 * gd.SECONDS_PER_DAY)
        assert days == 5

    def test_clamps_negative_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "1700000100\n")
        assert gd._last_change_days("foo.py", now_ts=1700000000) == 0

    def test_returns_none_for_untracked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        assert gd._last_change_days("missing.py") is None


class TestRiskFor:
    def test_aggregates_all_signals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(args: list[str]) -> str:
            if "--since=90.days.ago" in args:
                return "alice@x\nalice@x\nbob@x\n"
            if "-1" in args:
                return "1700000000\n"
            return 'feat: x\nRevert "bad"\n'

        monkeypatch.setattr(gd, "_run_git", fake)
        result = gd.risk_for("foo.py", now_ts=1700000000 + 3 * gd.SECONDS_PER_DAY)
        assert result == {
            "file": "foo.py",
            "authors_90d": 2,
            "changes_90d": 3,
            "reverts": 1,
            "last_change_days": 3,
            "staleness": "3 days ago",
        }

    def test_untracked_file_emits_negative_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "_run_git", lambda args: "")
        result = gd.risk_for("ghost.py")
        assert result == {
            "file": "ghost.py",
            "authors_90d": 0,
            "changes_90d": 0,
            "reverts": 0,
            "last_change_days": -1,
            "staleness": "untracked",
        }


# ─── orient bundle ───────────────────────────────────────────────────────────


class TestOrient:
    def test_bundles_all_five_with_summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gd,
            "hotspots",
            lambda: [
                {"file": "src/a.ts", "changes": 30},
                {"file": "src/b.ts", "changes": 12},
            ],
        )
        monkeypatch.setattr(
            gd,
            "bus_factor",
            lambda: [{"author": "Alice", "commits": 90, "percent": 75.0}],
        )
        monkeypatch.setattr(
            gd,
            "bug_clusters",
            lambda: [
                {"file": "src/a.ts", "bug_changes": 8},
                {"file": "src/c.ts", "bug_changes": 3},
            ],
        )
        monkeypatch.setattr(gd, "velocity", lambda: [{"month": "2025-01", "commits": 50}])
        monkeypatch.setattr(gd, "firefighting", lambda: [{"sha": "abc123", "subject": "Revert"}])
        result = gd.orient()
        assert result["summary"] == {
            "hotspot_count": 2,
            "bug_cluster_count": 2,
            "intersect_hotspot_bug": ["src/a.ts"],
            "top_author_pct": 75.0,
            "firefighting_count": 1,
        }
        assert result["hotspots"] == [
            {"file": "src/a.ts", "changes": 30},
            {"file": "src/b.ts", "changes": 12},
        ]
        assert result["bus_factor"] == [{"author": "Alice", "commits": 90, "percent": 75.0}]

    def test_empty_bus_factor_yields_zero_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gd, "hotspots", list)
        monkeypatch.setattr(gd, "bus_factor", list)
        monkeypatch.setattr(gd, "bug_clusters", list)
        monkeypatch.setattr(gd, "velocity", list)
        monkeypatch.setattr(gd, "firefighting", list)
        result = gd.orient()
        assert result["summary"]["top_author_pct"] == 0.0
        assert result["summary"]["intersect_hotspot_bug"] == []
