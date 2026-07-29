"""Detection of supported harnesses installed on this machine."""

from __future__ import annotations

import shutil
from pathlib import Path

from cheese_flow.models import HARNESS_NAMES, HarnessName

_CLI_NAMES: dict[HarnessName, tuple[str, ...]] = {
    "claude-code": ("claude",),
    "codex": ("codex",),
    "cursor": ("cursor-agent", "cursor"),
}

_CONFIG_DIRS: dict[HarnessName, str] = {
    "claude-code": ".claude",
    "codex": ".codex",
    "cursor": ".cursor",
}


def detect_available_harnesses() -> tuple[HarnessName, ...]:
    """Return the supported harnesses detected on this machine.

    A harness counts as available when its CLI is on ``PATH`` or its user
    configuration directory exists. No supported harness has a project-local
    installation signal, so detection takes no project root. The probe only
    reads, and detected harnesses start selected in the wizard.
    """
    home = Path.home()
    return tuple(name for name in HARNESS_NAMES if _is_available(name, home))


def _is_available(harness: HarnessName, home: Path) -> bool:
    if any(shutil.which(cli) is not None for cli in _CLI_NAMES[harness]):
        return True
    return _is_directory(home / _CONFIG_DIRS[harness])


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False
