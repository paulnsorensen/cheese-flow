"""Detection of supported harnesses installed on this machine."""

from __future__ import annotations

from pathlib import Path

from cheese_flow.models import HarnessName


def detect_available_harnesses(project_root: Path) -> tuple[HarnessName, ...]:
    """Return the supported harnesses detected for ``project_root``.

    Detected harnesses start selected in the wizard.
    """
    raise NotImplementedError
