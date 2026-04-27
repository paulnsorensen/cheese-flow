from __future__ import annotations

from pathlib import Path

import pytest
from milknado.config import graph_db_path
from milknado.domains.common import InvalidTransition, NodeStatus
from milknado.domains.graph import MikadoGraph, graph_summary


def _graph(root: Path) -> MikadoGraph:
    return MikadoGraph(graph_db_path(root))


def test_graph_summary_reports_empty_graph(tmp_path: Path) -> None:
    assert graph_summary(tmp_path) == "(empty graph)"


def test_add_node_persists_root_and_child(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    try:
        root = graph.add_node("root")
        child = graph.add_node("child", parent_id=root.id)

        assert root.id == 1
        assert child.parent_id == root.id
        assert [node.id for node in graph.get_children(root.id)] == [child.id]
    finally:
        graph.close()


def test_get_ready_nodes_excludes_root(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    try:
        root = graph.add_node("root")
        leaf = graph.add_node("leaf", parent_id=root.id)

        ready_ids = {node.id for node in graph.get_ready_nodes()}

        assert leaf.id in ready_ids
        assert root.id not in ready_ids
    finally:
        graph.close()


def test_invalid_transition_raises(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    try:
        node = graph.add_node("task")
        with pytest.raises(InvalidTransition, match="cannot transition") as exc_info:
            graph.mark_done(node.id)

        assert exc_info.value.current == NodeStatus.PENDING
        assert exc_info.value.target == NodeStatus.DONE
    finally:
        graph.close()


def test_done_node_is_terminal(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    try:
        node = graph.add_node("task")
        graph.mark_running(node.id)
        graph.mark_done(node.id)

        with pytest.raises(InvalidTransition, match="cannot transition"):
            graph.mark_running(node.id)
    finally:
        graph.close()


def test_add_node_requires_existing_parent(tmp_path: Path) -> None:
    graph = _graph(tmp_path)
    try:
        with pytest.raises(ValueError, match="Parent node 999 not found"):
            graph.add_node("child", parent_id=999)
    finally:
        graph.close()
