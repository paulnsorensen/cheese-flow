from __future__ import annotations

import sqlite3
from datetime import datetime

from milknado.domains.common import MikadoNode, NodeStatus


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            parent_id INTEGER,
            worktree_path TEXT,
            branch_name TEXT,
            run_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            dispatched_at TEXT,
            completion_duration_seconds REAL,
            oversized INTEGER NOT NULL DEFAULT 0,
            batch_index INTEGER
        );
        CREATE TABLE IF NOT EXISTS edges (
            parent_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            PRIMARY KEY (parent_id, child_id),
            FOREIGN KEY (parent_id) REFERENCES nodes(id),
            FOREIGN KEY (child_id) REFERENCES nodes(id)
        );
    """)


def row_to_node(row: sqlite3.Row) -> MikadoNode:
    completed_at_raw = row["completed_at"]
    dispatched_at_raw = row["dispatched_at"]
    return MikadoNode(
        id=row["id"],
        description=row["description"],
        status=NodeStatus(row["status"]),
        parent_id=row["parent_id"],
        worktree_path=row["worktree_path"],
        branch_name=row["branch_name"],
        run_id=row["run_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(datetime.fromisoformat(completed_at_raw) if completed_at_raw else None),
        dispatched_at=(datetime.fromisoformat(dispatched_at_raw) if dispatched_at_raw else None),
        oversized=bool(row["oversized"]),
        batch_index=row["batch_index"],
        completion_duration_seconds=row["completion_duration_seconds"],
    )
