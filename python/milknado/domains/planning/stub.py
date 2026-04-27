"""Stub planner — single-batch passthrough until the real solver lands.

The stub deliberately ignores ``depends_on`` and ``new_relationships``: it
does not topologically sort, split, or check token budgets. Its job is to
return a shape-correct ``BatchPlan`` so MCP callers can exercise the wire
format. Replace with the milknado solver in a follow-up pull.
"""

from __future__ import annotations

from collections.abc import Sequence

from .change import Batch, BatchPlan, FileChange, NewRelationship


def plan_batches_stub(
    changes: Sequence[FileChange],
    budget: int,
    new_relationships: Sequence[NewRelationship] = (),
) -> BatchPlan:
    """Return a single batch containing every change in input order.

    Args:
        changes: File changes to plan. Must have unique ids.
        budget: Token budget per batch. Accepted but unused by the stub.
        new_relationships: Extra precedence edges. Accepted but unused.

    Raises:
        ValueError: if change ids are not unique.
    """
    del budget, new_relationships  # documented as ignored
    seen: set[str] = set()
    for c in changes:
        if c.id in seen:
            raise ValueError(f"duplicate change id: {c.id!r}")
        seen.add(c.id)
    batch = Batch(
        index=0,
        change_ids=tuple(c.id for c in changes),
        depends_on=(),
        oversized=False,
    )
    return BatchPlan(batches=(batch,), spread_report=(), solver_status="STUB")
