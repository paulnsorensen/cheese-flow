"""Pure-function tests for tools.git_file_risk. Subprocess paths mocked."""

from __future__ import annotations

import json

import pytest
from tools import git_file_risk as gfr


class TestHumanizeStaleness:
    def test_untracked_when_none(self) -> None:
        assert gfr.humanize_staleness(None) == "untracked"

    def test_today_when_zero(self) -> None:
        assert gfr.humanize_staleness(0) == "today"

    def test_singular_day(self) -> None:
        assert gfr.humanize_staleness(1) == "1 day ago"

    @pytest.mark.parametrize("days,expected", [(2, "2 days ago"), (29, "29 days ago")])
    def test_plural_days_under_month(self, days: int, expected: str) -> None:
        assert gfr.humanize_staleness(days) == expected

    @pytest.mark.parametrize(
        "days,expected",
        [(30, "1 month ago"), (60, "2 months ago"), (200, "7 months ago")],
    )
    def test_months(self, days: int, expected: str) -> None:
        assert gfr.humanize_staleness(days) == expected

    @pytest.mark.parametrize(
        "days,expected", [(365, "1 year ago"), (730, "2 years ago"), (1825, "5 years ago")]
    )
    def test_years(self, days: int, expected: str) -> None:
        assert gfr.humanize_staleness(days) == expected


class TestAuthorsAndChanges90d:
    def test_counts_distinct_and_total(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, list[str]] = {}

        def fake(args: list[str]) -> str:
            captured["args"] = args
            return "alice@x\nbob@x\nalice@x\n"

        monkeypatch.setattr(gfr, "_run_git", fake)
        authors, changes = gfr.authors_and_changes_90d("foo.py")
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
        monkeypatch.setattr(gfr, "_run_git", lambda args: "")
        assert gfr.authors_and_changes_90d("foo.py") == (0, 0)


class TestRevertCount:
    def test_counts_revert_subjects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        log = 'feat: x\nRevert "bad"\nRevert "another"\nfix: y\n'
        monkeypatch.setattr(gfr, "_run_git", lambda args: log)
        assert gfr.revert_count("foo.py") == 2

    def test_zero_when_no_reverts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gfr, "_run_git", lambda args: "feat: x\nfix: y\n")
        assert gfr.revert_count("foo.py") == 0

    def test_does_not_match_substring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # "covert" contains "vert" but does not start with "Revert"
        monkeypatch.setattr(gfr, "_run_git", lambda args: "covert refactor\n")
        assert gfr.revert_count("foo.py") == 0


class TestLastChangeDays:
    def test_computes_days_from_unix_ts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gfr, "_run_git", lambda args: "1700000000\n")
        days = gfr.last_change_days("foo.py", now_ts=1700000000 + 5 * gfr.SECONDS_PER_DAY)
        assert days == 5

    def test_clamps_negative_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # File timestamp in the future relative to now_ts → clamp to 0.
        monkeypatch.setattr(gfr, "_run_git", lambda args: "1700000100\n")
        assert gfr.last_change_days("foo.py", now_ts=1700000000) == 0

    def test_returns_none_for_untracked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gfr, "_run_git", lambda args: "")
        assert gfr.last_change_days("missing.py") is None


class TestRiskFor:
    def test_aggregates_all_signals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(args: list[str]) -> str:
            if "--since=90.days.ago" in args:
                return "alice@x\nalice@x\nbob@x\n"
            if "-1" in args:
                return "1700000000\n"
            return 'feat: x\nRevert "bad"\n'

        monkeypatch.setattr(gfr, "_run_git", fake)
        result = gfr.risk_for("foo.py", now_ts=1700000000 + 3 * gfr.SECONDS_PER_DAY)
        assert result == {
            "file": "foo.py",
            "authors_90d": 2,
            "changes_90d": 3,
            "reverts": 1,
            "last_change_days": 3,
            "staleness": "3 days ago",
        }

    def test_untracked_file_emits_negative_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gfr, "_run_git", lambda args: "")
        result = gfr.risk_for("ghost.py")
        assert result["last_change_days"] == -1
        assert result["staleness"] == "untracked"
        assert result["authors_90d"] == 0
        assert result["changes_90d"] == 0
        assert result["reverts"] == 0


class TestMain:
    def test_no_args_prints_usage_and_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = gfr.main([])
        captured = capsys.readouterr()
        assert rc == 2
        assert "usage" in captured.err
        assert captured.out == ""

    def test_emits_json_array_for_each_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gfr, "risk_for", lambda p, now_ts=None: {"file": p, "marker": True})
        rc = gfr.main(["a.py", "b.py"])
        out = capsys.readouterr().out.strip()
        assert rc == 0
        assert json.loads(out) == [
            {"file": "a.py", "marker": True},
            {"file": "b.py", "marker": True},
        ]
