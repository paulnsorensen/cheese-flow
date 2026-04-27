"""DB schema creation and row serialization helpers for MikadoGraph."""

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


def ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    for column_name, ddl in [
        ("run_id", "ALTER TABLE nodes ADD COLUMN run_id TEXT"),
        (
            "completion_duration_seconds",
            "ALTER TABLE nodes ADD COLUMN completion_duration_seconds REAL",
        ),
        ("dispatched_at", "ALTER TABLE nodes ADD COLUMN dispatched_at TEXT"),
        (
            "oversized",
            "ALTER TABLE nodes ADD COLUMN oversized INTEGER NOT NULL DEFAULT 0",
        ),
        ("batch_index", "ALTER TABLE nodes ADD COLUMN batch_index INTEGER"),
    ]:
        if column_name not in columns:
            conn.execute(ddl)
            conn.commit()


def row_to_node(row: sqlite3.Row) -> MikadoNode:
    keys = row.keys()
    completed_at_raw = row["completed_at"] if "completed_at" in keys else None
    dispatched_at_raw = row["dispatched_at"] if "dispatched_at" in keys else None
    completion_duration = (
        row["completion_duration_seconds"] if "completion_duration_seconds" in keys else None
    )
    return MikadoNode(
        id=row["id"],
        description=row["description"],
        status=NodeStatus(row["status"]),
        parent_id=row["parent_id"],
        worktree_path=row["worktree_path"],
        branch_name=row["branch_name"],
        run_id=row["run_id"] if "run_id" in keys else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(datetime.fromisoformat(completed_at_raw) if completed_at_raw else None),
        dispatched_at=(datetime.fromisoformat(dispatched_at_raw) if dispatched_at_raw else None),
        oversized=bool(row["oversized"]) if "oversized" in keys else False,
        batch_index=row["batch_index"] if "batch_index" in keys else None,
        completion_duration_seconds=completion_duration,
    )
