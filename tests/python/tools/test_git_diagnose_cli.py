"""CLI dispatch tests for tools.git_diagnose."""

from __future__ import annotations

import json

import pytest
from tools import git_diagnose as gd


class TestMain:
    def test_no_args_exits_with_argparse_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            gd.main([])
        assert exc_info.value.code == 2

    def test_hotspots_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        captured: dict[str, object] = {}

        def fake_hotspots(since: str = gd.DEFAULT_SINCE, limit: int = gd.DEFAULT_LIMIT):
            captured["since"] = since
            captured["limit"] = limit
            return [{"file": "x.ts", "changes": 5}]

        monkeypatch.setattr(gd, "hotspots", fake_hotspots)
        rc = gd.main(["hotspots", "--since", "6.months.ago", "--limit", "3"])
        out = capsys.readouterr().out.strip()
        assert rc == 0
        assert json.loads(out) == [{"file": "x.ts", "changes": 5}]
        assert captured == {"since": "6.months.ago", "limit": 3}

    def test_bus_factor_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            gd, "bus_factor", lambda limit=10: [{"author": "A", "commits": 1, "percent": 100.0}]
        )
        rc = gd.main(["bus-factor"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out.strip()) == [
            {"author": "A", "commits": 1, "percent": 100.0}
        ]

    def test_velocity_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gd, "velocity", lambda: [{"month": "2025-01", "commits": 1}])
        rc = gd.main(["velocity"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out.strip()) == [{"month": "2025-01", "commits": 1}]

    def test_firefighting_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            gd, "firefighting", lambda since=gd.DEFAULT_SINCE: [{"sha": "abc", "subject": "x"}]
        )
        rc = gd.main(["firefighting"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out.strip()) == [{"sha": "abc", "subject": "x"}]

    def test_risk_subcommand_emits_array_per_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gd, "risk_for", lambda p, now_ts=None: {"file": p, "marker": True})
        rc = gd.main(["risk", "a.py", "b.py"])
        out = capsys.readouterr().out.strip()
        assert rc == 0
        assert json.loads(out) == [
            {"file": "a.py", "marker": True},
            {"file": "b.py", "marker": True},
        ]

    def test_orient_subcommand(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gd, "orient", lambda: {"hotspots": [], "summary": {"hotspot_count": 0}})
        rc = gd.main(["orient"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out.strip()) == {
            "hotspots": [],
            "summary": {"hotspot_count": 0},
        }
