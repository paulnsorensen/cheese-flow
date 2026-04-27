"""Graph slice stub — refuses to fake persisted state.

Once the milknado sqlite back-end lands, replace ``graph_summary_stub`` with
a real ``MikadoGraph`` query and ``add_node_stub`` with an ``add_node`` call.
The shapes here mirror the upstream return values so the MCP tool surface
stays callable.
"""

from __future__ import annotations

from pathlib import Path


def graph_summary_stub(root: Path) -> str:
    """Return the same string upstream emits for an empty database."""
    del root  # accepted for parity with the eventual real implementation
    return "(empty graph)"


def add_node_stub(
    description: str,
    parent_id: int | None,
    root: Path,
) -> str:
    """Refuse to fabricate a node id.

    The real implementation persists the node and returns its id. A stub that
    returned a fake id (e.g. 0) would invite agents to chain ``parent_id=0``
    against vapor state. Raising signals to the MCP shim that no id is
    available and the call should surface as a stub marker, not a success.
    """
    del description, parent_id, root
    raise NotImplementedError("milknado_add_node requires the graph back-end; not yet wired")
