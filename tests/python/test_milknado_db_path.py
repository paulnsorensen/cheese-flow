"""Verifies MikadoGraph initialises the database at the config-derived path."""

from __future__ import annotations

from pathlib import Path

from milknado.domains.common.config import default_config
from milknado.domains.graph.graph import MikadoGraph


def test_default_config_db_path_is_in_repo(tmp_path: Path) -> None:
    cfg = default_config(tmp_path)
    assert cfg.db_path == tmp_path / ".milknado" / "milknado.db"


def test_mikado_graph_creates_db_at_config_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = default_config(repo)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    graph = MikadoGraph(cfg.db_path)
    try:
        graph.add_node("seed")
    finally:
        graph.close()

    assert cfg.db_path.exists(), "graph must initialise the db at the config-derived path"
