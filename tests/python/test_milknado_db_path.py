"""Verifies MILKNADO_DB_PATH env override takes precedence over the in-repo default."""

from __future__ import annotations

from pathlib import Path

import pytest
from milknado.config import graph_db_path
from milknado.domains.graph import MikadoGraph


def test_graph_db_path_default_is_in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MILKNADO_DB_PATH", raising=False)

    assert graph_db_path(tmp_path) == tmp_path / ".milknado" / "milknado.db"


def test_graph_db_path_honors_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "override" / "milknado.db"
    monkeypatch.setenv("MILKNADO_DB_PATH", str(override))

    assert graph_db_path(tmp_path) == override


def test_mikado_graph_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    override = tmp_path / "cheese-home" / "milknado.db"
    override.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MILKNADO_DB_PATH", str(override))

    db_path = graph_db_path(repo)
    graph = MikadoGraph(db_path)
    try:
        graph.add_node("seed")
    finally:
        graph.close()

    assert override.exists(), "graph must initialise the db at the env-override path"
    assert not (repo / ".milknado").exists(), (
        "graph must not touch the in-repo default when env override is set"
    )


def test_graph_db_path_blank_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MILKNADO_DB_PATH", "   ")

    assert graph_db_path(tmp_path) == tmp_path / ".milknado" / "milknado.db"
