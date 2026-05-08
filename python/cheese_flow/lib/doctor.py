"""Port of `src/lib/doctor.ts` — tool dependency checks for ``cheese doctor``.

Mirrors the TS surface: ``TOOL_CHECKS`` (list of ``ToolCheck``),
``run_tool_check``, ``run_all_tool_checks``, ``format_report``, and
``has_blocking_failure``. The TS module spawns each binary with
``--version`` via ``child_process.spawn``; the port uses
``asyncio.create_subprocess_exec`` so ``Promise.all`` becomes
``asyncio.gather`` per decision 6 (no async redesign).

The TS module prepends ``<repo>/node_modules/.bin`` to ``PATH`` so the
bundled ``tilth`` binary is reachable. The port preserves that behaviour
by computing the same path relative to ``__file__``: from
``python/cheese_flow/lib/doctor.py`` the repo root is three parents up.
The npm-bundled bin directory disappears in US-017 (TS cutover); until
then it stays so Python and TS doctor invocations agree.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ToolTier = Literal["required", "recommended", "suggested"]

BUNDLED_BIN_DIR: str = str(Path(__file__).resolve().parents[3] / "node_modules" / ".bin")


@dataclass(frozen=True)
class ToolCheck:
    name: str
    tier: ToolTier
    purpose: str
    installHint: str


@dataclass(frozen=True)
class ToolResult:
    name: str
    tier: ToolTier
    purpose: str
    installHint: str
    ok: bool
    version: str | None = None
    error: str | None = None


TOOL_CHECKS: list[ToolCheck] = [
    ToolCheck(
        name="tilth",
        tier="required",
        purpose="Tree-sitter code intelligence used by exploration skills.",
        installHint=(
            "Bundled with cheese-flow. If missing, install globally: "
            "npm install -g cheese-flow"
        ),
    ),
    ToolCheck(
        name="mergiraf",
        tier="recommended",
        purpose="Syntax-aware merge driver for resolving conflicts cleanly.",
        installHint="brew install mergiraf  (or: cargo install mergiraf)",
    ),
    ToolCheck(
        name="rtk",
        tier="suggested",
        purpose="Token-optimized CLI proxy for Claude Code sessions.",
        installHint="cargo install rtk-cli",
    ),
]


def _spawn_env() -> dict[str, str]:
    env = dict(os.environ)
    existing_path = env.get("PATH", "")
    env["PATH"] = (
        f"{BUNDLED_BIN_DIR}{os.pathsep}{existing_path}"
        if existing_path
        else BUNDLED_BIN_DIR
    )
    return env


def _result(
    check: ToolCheck,
    *,
    ok: bool,
    version: str | None = None,
    error: str | None = None,
) -> ToolResult:
    return ToolResult(
        name=check.name,
        tier=check.tier,
        purpose=check.purpose,
        installHint=check.installHint,
        ok=ok,
        version=version,
        error=error,
    )


async def run_tool_check(check: ToolCheck) -> ToolResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            check.name,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_spawn_env(),
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return _result(check, ok=False, error=str(exc))

    stdout_bytes, stderr_bytes = await proc.communicate()
    code = proc.returncode
    if code == 0:
        text = (stdout_bytes.decode() or stderr_bytes.decode()).strip()
        first_line = text.split("\n")[0] if text else ""
        if first_line:
            return _result(check, ok=True, version=first_line)
        return _result(check, ok=True)
    code_label = str(code) if code is not None else "unknown"
    return _result(check, ok=False, error=f"exited with code {code_label}")


async def run_all_tool_checks() -> list[ToolResult]:
    return list(await asyncio.gather(*(run_tool_check(c) for c in TOOL_CHECKS)))


_TIER_LABELS: dict[ToolTier, str] = {
    "required": "REQUIRED",
    "recommended": "RECOMMENDED",
    "suggested": "SUGGESTED",
}


def format_report(results: list[ToolResult]) -> str:
    lines: list[str] = ["cheese doctor — tool dependency check", ""]
    for result in results:
        status = "ok" if result.ok else "missing"
        tag = _TIER_LABELS[result.tier]
        lines.append(f"[{tag}] {result.name}: {status}")
        lines.append(f"  {result.purpose}")
        if result.ok and result.version:
            lines.append(f"  found: {result.version}")
        elif result.ok:
            lines.append("  found")
        else:
            lines.append(f"  install: {result.installHint}")
        lines.append("")
    return "\n".join(lines)


def has_blocking_failure(results: list[ToolResult]) -> bool:
    return any(r.tier == "required" and not r.ok for r in results)


__all__ = [
    "BUNDLED_BIN_DIR",
    "TOOL_CHECKS",
    "ToolCheck",
    "ToolResult",
    "ToolTier",
    "format_report",
    "has_blocking_failure",
    "run_all_tool_checks",
    "run_tool_check",
]
