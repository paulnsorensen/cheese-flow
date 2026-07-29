"""The linear Cheese Flow install wizard."""

from __future__ import annotations

from cheese_flow.models import DesiredState


def run_wizard(initial: DesiredState | None) -> DesiredState | None:
    """Run ``Preflight -> ... -> Apply``, returning the accepted state.

    ``initial`` prefills every screen without skipping any. Returns ``None`` when
    the user cancels before Apply, in which case no managed state is written.
    """
    raise NotImplementedError
