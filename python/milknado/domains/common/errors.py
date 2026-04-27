from __future__ import annotations

from typing import Any


class MilknadoError(Exception):
    """Base for milknado-specific exceptions."""


class InvalidTransition(MilknadoError, ValueError):
    def __init__(
        self,
        node_id: int,
        current: Any,
        target: Any,
        valid_targets: tuple[Any, ...],
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
