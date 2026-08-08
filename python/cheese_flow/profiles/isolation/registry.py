"""Closed dispatch registry for isolated profile launches."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.isolation.claude import build_claude_isolation
from cheese_flow.profiles.isolation.codex import build_codex_isolation
from cheese_flow.profiles.isolation.opencode import build_opencode_isolation
from cheese_flow.profiles.launch_policy import ValidatedLaunchPolicy
from cheese_flow.profiles.models import LaunchHarnessName, LaunchSpec
from cheese_flow.profiles.parse import ResolvedProfile


class IsolationBuilder(Protocol):
    def __call__(
        self,
        profile: ResolvedProfile,
        policy: ValidatedLaunchPolicy,
        workspace: Path,
        *,
        environment: Mapping[str, str],
    ) -> LaunchSpec: ...


_ISOLATION_BUILDERS: Mapping[str, IsolationBuilder] = {
    "claude": build_claude_isolation,
    "codex": build_codex_isolation,
    "opencode": build_opencode_isolation,
}


def isolation_builder_for(harness: LaunchHarnessName) -> IsolationBuilder:
    """Return the isolated-launch builder for one supported harness."""
    try:
        return _ISOLATION_BUILDERS[harness]
    except KeyError:
        raise ProfileLaunchError(
            f"isolated launch is unsupported for harness {harness!r}"
        ) from None


__all__ = ["IsolationBuilder", "isolation_builder_for"]
