from __future__ import annotations

from .types import NodeStatus


class InvalidTransition(ValueError):
    def __init__(
        self,
        node_id: int,
        current: NodeStatus,
        target: NodeStatus,
        valid_targets: tuple[NodeStatus, ...],
    ) -> None:
        self.node_id = node_id
        self.current = current
        self.target = target
        self.valid_targets = valid_targets
        valid_str = ", ".join(sorted(value.value for value in valid_targets))
        super().__init__(
            f"Node {node_id}: cannot transition from {current.value} "
            f"to {target.value}. Valid: [{valid_str}]"
        )
