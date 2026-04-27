from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from milknado.config import graph_db_path
from milknado.domains.common import (
    VALID_TRANSITIONS,
    InvalidTransition,
    MikadoEdge,
    MikadoNode,
    NodeStatus,
)
from milknado.domains.graph._persistence import (
    create_tables,
    ensure_schema,
    row_to_node,
)


class MikadoGraph:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        create_tables(self._conn)
        ensure_schema(self._conn)

    def add_node(
        self,
        description: str,
        parent_id: int | None = None,
        *,
        oversized: bool = False,
        batch_index: int | None = None,
    ) -> MikadoNode:
        if parent_id is not None and self.get_node(parent_id) is None:
            raise ValueError(f"Parent node {parent_id} not found")
        now = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "INSERT INTO nodes "
            "(description, status, parent_id, created_at, oversized, batch_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                description,
                NodeStatus.PENDING.value,
                parent_id,
                now,
                1 if oversized else 0,
                batch_index,
            ),
        )
        self._conn.commit()
        node_id = cur.lastrowid
        assert node_id is not None
        if parent_id is not None:
            self.add_edge(parent_id, node_id)
        row = self._conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        assert row is not None
        return row_to_node(row)

    def add_edge(self, parent_id: int, child_id: int) -> MikadoEdge:
        if self._creates_cycle(parent_id, child_id):
            raise ValueError(f"Edge {parent_id}->{child_id} would create a cycle")
        self._conn.execute(
            "INSERT INTO edges (parent_id, child_id) VALUES (?, ?)",
            (parent_id, child_id),
        )
        self._conn.commit()
        return MikadoEdge(parent_id=parent_id, child_id=child_id)

    def get_node(self, node_id: int) -> MikadoNode | None:
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        return row_to_node(row) if row else None

    def get_all_nodes(self) -> list[MikadoNode]:
        rows = self._conn.execute("SELECT * FROM nodes ORDER BY id").fetchall()
        return [row_to_node(row) for row in rows]

    def get_children(self, node_id: int) -> list[MikadoNode]:
        rows = self._conn.execute(
            "SELECT n.* FROM nodes n "
            "JOIN edges e ON n.id = e.child_id "
            "WHERE e.parent_id = ? ORDER BY n.id",
            (node_id,),
        ).fetchall()
        return [row_to_node(row) for row in rows]

    def get_root(self) -> MikadoNode | None:
        row = self._conn.execute(
            "SELECT * FROM nodes "
            "WHERE id NOT IN (SELECT DISTINCT child_id FROM edges) "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        return row_to_node(row) if row else None

    def get_ready_nodes(self) -> list[MikadoNode]:
        root = self.get_root()
        ready: list[MikadoNode] = []
        for node in self.get_all_nodes():
            if node.status != NodeStatus.PENDING:
                continue
            if root is not None and node.id == root.id:
                continue
            children = self.get_children(node.id)
            if not children or all(child.status == NodeStatus.DONE for child in children):
                ready.append(node)
        return ready

    def mark_running(
        self,
        node_id: int,
        worktree_path: str | None = None,
        branch_name: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self._assert_transition(node_id, NodeStatus.RUNNING)
        self._conn.execute(
            "UPDATE nodes SET status = ?, completed_at = NULL, "
            "worktree_path = ?, branch_name = ?, run_id = ? WHERE id = ?",
            (NodeStatus.RUNNING.value, worktree_path, branch_name, run_id, node_id),
        )
        self._conn.commit()

    def mark_done(self, node_id: int) -> None:
        self._assert_transition(node_id, NodeStatus.DONE)
        self._conn.execute(
            "UPDATE nodes SET status = ?, completed_at = ? WHERE id = ?",
            (NodeStatus.DONE.value, datetime.now(UTC).isoformat(), node_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _assert_transition(self, node_id: int, target: NodeStatus) -> None:
        node = self.get_node(node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found")
        allowed = VALID_TRANSITIONS.get(node.status, set())
        if target not in allowed:
            raise InvalidTransition(
                node_id=node_id,
                current=node.status,
                target=target,
                valid_targets=tuple(allowed),
            )

    def _creates_cycle(self, parent_id: int, child_id: int) -> bool:
        visited: set[int] = set()
        stack = [parent_id]
        while stack:
            current = stack.pop()
            if current == child_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            rows = self._conn.execute(
                "SELECT parent_id FROM edges WHERE child_id = ?",
                (current,),
            ).fetchall()
            stack.extend(row[0] for row in rows)
        return False


def graph_summary(root: Path) -> str:
    graph = MikadoGraph(graph_db_path(root))
    try:
        nodes = graph.get_all_nodes()
        if not nodes:
            return "(empty graph)"
        return "\n".join(
            f"id={node.id} status={node.status.value} desc={node.description[:120]!r}"
            for node in nodes
        )
    finally:
        graph.close()


def add_node(description: str, parent_id: int | None, root: Path) -> str:
    graph = MikadoGraph(graph_db_path(root))
    try:
        node = graph.add_node(description, parent_id=parent_id)
        return f"created node id={node.id} description={node.description!r}"
    finally:
        graph.close()
