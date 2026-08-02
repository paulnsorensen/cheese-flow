"""Grade the JSON report from a real ``cheese install`` run.

The smoke test's whole value is that it ran the real children, so its
assertion has to read what they actually did. A nonzero exit from
``bootstrap.sh`` catches a crash or a timeout; this catches the quieter
failure where the run exits 0 with a step that never converged.

Deliberately dependency-free: the smoke job installs cheese-flow into a
throwaway HOME and must be able to grade the result without importing it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONVERGED = frozenset({"succeeded", "skipped"})


def main(report_path: Path) -> int:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"smoke: no readable report at {report_path}: {error}", file=sys.stderr)
        return 1

    results = report.get("results", ())
    if not results:
        print("smoke: the run planned nothing — no step was executed", file=sys.stderr)
        return 1

    for result in results:
        print(f"  {result['status']:12} {result['component']:14} {result['phase']}")

    unconverged = [result for result in results if result["status"] not in CONVERGED]
    status = report.get("status")
    if status != "succeeded" or unconverged:
        print(f"\nsmoke: run reported {status!r}", file=sys.stderr)
        for result in unconverged:
            print(
                f"\n  {result['component']} / {result['phase']}: {result['status']}",
                file=sys.stderr,
            )
            print(f"    argv: {' '.join(result.get('argv') or ())}", file=sys.stderr)
            print(f"    postcondition: {result['postcondition']}", file=sys.stderr)
            if result.get("stderr_tail"):
                print(f"    stderr: {result['stderr_tail']}", file=sys.stderr)
            if result.get("remediation"):
                print(f"    remediation: {result['remediation']}", file=sys.stderr)
        return 1

    print(f"\nsmoke: {len(results)} steps converged")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
