from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


VALID_TRANSITIONS: Mapping[NodeStatus, frozenset[NodeStatus]] = MappingProxyType(
    {
        NodeStatus.PENDING: frozenset({NodeStatus.RUNNING, NodeStatus.BLOCKED, NodeStatus.FAILED}),
        NodeStatus.RUNNING: frozenset(
            {
                NodeStatus.DONE,
                NodeStatus.FAILED,
                NodeStatus.BLOCKED,
                NodeStatus.PENDING,
            }
        ),
        NodeStatus.BLOCKED: frozenset({NodeStatus.PENDING}),
        NodeStatus.FAILED: frozenset({NodeStatus.PENDING}),
        NodeStatus.DONE: frozenset(),
    }
)


@dataclass(frozen=True)
class MikadoNode:
    id: int
    description: str
    status: NodeStatus = NodeStatus.PENDING
    parent_id: int | None = None
    worktree_path: str | None = None
    branch_name: str | None = None
    run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    dispatched_at: datetime | None = None
    oversized: bool = False
    batch_index: int | None = None
    completion_duration_seconds: float | None = None


@dataclass(frozen=True)
class MikadoEdge:
    parent_id: int
    child_id: int
