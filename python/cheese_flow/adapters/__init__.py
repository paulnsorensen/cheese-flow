"""cheese-flow harness adapters.

Houses the ports of `src/adapters/*.ts` (claude-code, codex, cursor,
copilot-cli, and the shared manifest builders).
"""

from __future__ import annotations

from cheese_flow.adapters.claude_code import claude_code_adapter
from cheese_flow.adapters.codex import codex_adapter
from cheese_flow.adapters.copilot_cli import copilot_cli_adapter
from cheese_flow.adapters.cursor import cursor_adapter
from cheese_flow.lib.harness import HarnessAdapter, HarnessName

HARNESS_ADAPTERS: dict[HarnessName, HarnessAdapter] = {
    "claude-code": claude_code_adapter,
    "codex": codex_adapter,
    "cursor": cursor_adapter,
    "copilot-cli": copilot_cli_adapter,
}

HARNESS_NAMES: tuple[HarnessName, ...] = tuple(HARNESS_ADAPTERS.keys())

__all__ = [
    "HARNESS_ADAPTERS",
    "HARNESS_NAMES",
    "claude_code_adapter",
    "codex_adapter",
    "copilot_cli_adapter",
    "cursor_adapter",
]
