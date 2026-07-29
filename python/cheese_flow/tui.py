"""The linear Cheese Flow install wizard.

Six screens, one prompt at a time, every byte on stderr so the CLI keeps stdout
free for its final JSON document. Input is line oriented: digits toggle entries,
an empty line accepts the screen, ``b`` steps back, ``q`` cancels.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from cheese_flow.harness_detection import detect_available_harnesses
from cheese_flow.models import (
    COMPONENT_NAMES,
    DEFAULT_MAX_DEPTH,
    HARNESS_NAMES,
    REQUIRED_COMPONENTS,
    ComponentName,
    DesiredState,
    HarnessName,
    RepositoryCandidate,
    RepositorySelection,
    canonicalize,
)
from cheese_flow.repositories import discover_repositories

_NEXT = "next"
_BACK = "back"
_CANCEL = "cancel"

_TOGGLE_HINT = "Toggle numbers, Enter to continue, b back, q quit:"


@dataclass
class _Draft:
    """Mutable wizard state, prefilled from an existing manifest when present."""

    detected: tuple[HarnessName, ...]
    harnesses: list[HarnessName]
    components: list[ComponentName]
    search_roots: list[Path]
    max_depth: int
    selected: list[Path]
    candidates: list[Path] = field(default_factory=list)


def run_wizard(initial: DesiredState | None) -> DesiredState | None:
    """Run ``Preflight -> ... -> Apply``, returning the accepted state.

    ``initial`` prefills every screen without skipping any. Returns ``None`` when
    the user cancels before Apply, in which case no managed state is written.
    """
    console = Console(stderr=True, markup=False, highlight=False, soft_wrap=True)
    draft = _draft_from(initial)
    screens = (_preflight, _harnesses, _components, _search_roots, _repositories, _preview)

    index = 0
    while index < len(screens):
        verdict = screens[index](console, draft)
        if verdict == _CANCEL:
            console.print("Cancelled. Nothing was installed and no manifest was written.")
            return None
        index = index + 1 if verdict == _NEXT else max(0, index - 1)
    return _build(draft)


def _draft_from(initial: DesiredState | None) -> _Draft:
    detected = detect_available_harnesses()
    if initial is None:
        return _Draft(
            detected=detected,
            harnesses=list(detected),
            components=list(REQUIRED_COMPONENTS),
            search_roots=[],
            max_depth=DEFAULT_MAX_DEPTH,
            selected=[],
        )
    return _Draft(
        detected=detected,
        harnesses=list(initial.harnesses),
        components=list(initial.components),
        search_roots=list(initial.repositories.search_roots),
        max_depth=initial.repositories.max_depth,
        selected=list(initial.repositories.selected),
    )


# ─── Screens ─────────────────────────────────────────────────────────────────


def _preflight(console: Console, draft: _Draft) -> str:
    console.print("[1/6] Preflight")
    detected = ", ".join(draft.detected) if draft.detected else "none"
    console.print(f"  Detected harnesses: {detected}")
    console.print("  Hallouminate and easy-cheese are required; Tilth is optional.")
    return _command(console, "Enter to continue, q quit:", allow_back=False)


def _harnesses(console: Console, draft: _Draft) -> str:
    console.print("[2/6] Harnesses")
    labels = [f"{name} (detected)" if name in draft.detected else name for name in HARNESS_NAMES]
    while True:
        _render_options(console, labels, [name in draft.harnesses for name in HARNESS_NAMES])
        verdict, picks = _toggles(console, len(HARNESS_NAMES))
        if verdict != _NEXT:
            return verdict
        if picks:
            for pick in picks:
                _flip(draft.harnesses, HARNESS_NAMES[pick])
            continue
        if not draft.harnesses:
            console.print("  Select at least one harness.")
            continue
        return _NEXT


def _components(console: Console, draft: _Draft) -> str:
    console.print("[3/6] Components")
    labels = [
        f"{name} (required)" if name in REQUIRED_COMPONENTS else name for name in COMPONENT_NAMES
    ]
    while True:
        _render_options(console, labels, [name in draft.components for name in COMPONENT_NAMES])
        verdict, picks = _toggles(console, len(COMPONENT_NAMES))
        if verdict != _NEXT:
            return verdict
        if not picks:
            return _NEXT
        for pick in picks:
            name = COMPONENT_NAMES[pick]
            if name in REQUIRED_COMPONENTS:
                console.print(f"  {name} is required and cannot be deselected.")
                continue
            _flip(draft.components, name)


def _search_roots(console: Console, draft: _Draft) -> str:
    console.print("[4/6] Search roots")
    while True:
        current = ", ".join(str(root) for root in draft.search_roots) or "none"
        console.print(f"  Current: {current}")
        console.print(f"  Depth {draft.max_depth} (0 means the root directory itself)")
        answer = _ask(console, "Comma-separated absolute paths, Enter to keep, b back, q quit:")
        verdict = _verdict(answer)
        if verdict is not None:
            return verdict
        if answer:
            roots = _parse_roots(console, answer)
            if roots is None:
                continue
            draft.search_roots = roots
        if _read_depth(console, draft) == _CANCEL:
            return _CANCEL
        return _NEXT


def _repositories(console: Console, draft: _Draft) -> str:
    draft.candidates = _candidate_paths(draft)
    console.print("[5/6] Repository candidates")
    if not draft.candidates:
        console.print("  No repositories found under the search roots.")
    while True:
        _render_options(
            console,
            [str(path) for path in draft.candidates],
            [path in draft.selected for path in draft.candidates],
        )
        verdict, picks = _toggles(console, len(draft.candidates))
        if verdict != _NEXT:
            return verdict
        if not picks:
            return _NEXT
        for pick in picks:
            _flip(draft.selected, draft.candidates[pick])


def _preview(console: Console, draft: _Draft) -> str:
    console.print("[6/6] Preview")
    console.print(f"  Harnesses:    {', '.join(_ordered(draft.harnesses, HARNESS_NAMES))}")
    console.print(f"  Components:   {', '.join(_ordered(draft.components, COMPONENT_NAMES))}")
    console.print(f"  Search roots: {', '.join(str(r) for r in draft.search_roots) or 'none'}")
    console.print(f"  Max depth:    {draft.max_depth}")
    console.print(f"  Repositories: {', '.join(str(p) for p in draft.selected) or 'none'}")
    return _command(console, "Enter to apply, b back, q quit:", allow_back=True)


# ─── Prompt plumbing ─────────────────────────────────────────────────────────


def _ask(console: Console, prompt: str) -> str | None:
    """Print ``prompt`` on stderr and read one line. ``None`` means end of input."""
    console.print(prompt, end=" ")
    line = sys.stdin.readline()
    if line == "":
        console.print("")
        return None
    return line.strip()


def _verdict(answer: str | None) -> str | None:
    if answer is None or answer.lower() == "q":
        return _CANCEL
    if answer.lower() == "b":
        return _BACK
    return None


def _command(console: Console, prompt: str, *, allow_back: bool) -> str:
    while True:
        answer = _ask(console, prompt)
        verdict = _verdict(answer)
        if verdict == _CANCEL:
            return _CANCEL
        if verdict == _BACK:
            if allow_back:
                return _BACK
            console.print("  Already at the first screen.")
            continue
        if answer:
            console.print(f"  Unrecognized input: {answer}")
            continue
        return _NEXT


def _toggles(console: Console, count: int) -> tuple[str, list[int]]:
    """Read one toggle line, returning a verdict and the zero-based picks."""
    while True:
        answer = _ask(console, _TOGGLE_HINT)
        verdict = _verdict(answer)
        if verdict is not None:
            return verdict, []
        if not answer:
            return _NEXT, []
        picks: list[int] = []
        rejected = False
        for token in answer.replace(",", " ").split():
            if not token.isdigit() or not 1 <= int(token) <= count:
                console.print(f"  Not a listed number: {token}")
                rejected = True
                break
            picks.append(int(token) - 1)
        if not rejected:
            return _NEXT, picks


def _render_options(console: Console, labels: list[str], checked: list[bool]) -> None:
    for number, (label, mark) in enumerate(zip(labels, checked, strict=True), start=1):
        console.print(f"  {number}. [{'x' if mark else ' '}] {label}")


def _read_depth(console: Console, draft: _Draft) -> str:
    while True:
        answer = _ask(console, f"Max depth [{draft.max_depth}], Enter to keep, q quit:")
        if answer is None or answer.lower() == "q":
            return _CANCEL
        if not answer:
            return _NEXT
        if answer.isdigit():
            draft.max_depth = int(answer)
            return _NEXT
        console.print("  Max depth must be a non-negative integer.")


def _parse_roots(console: Console, answer: str) -> list[Path] | None:
    roots: list[Path] = []
    for token in answer.split(","):
        text = token.strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_absolute():
            console.print(f"  Search roots must be absolute paths: {text}")
            return None
        # Discovery canonicalizes what it finds, so the root has to be
        # canonicalized too or a symlinked root never contains its own results.
        canonical = canonicalize(path)
        if canonical not in roots:
            roots.append(canonical)
    return roots


def _candidate_paths(draft: _Draft) -> list[Path]:
    """Discovered repositories, plus any prefilled selection discovery missed."""
    discovered: tuple[RepositoryCandidate, ...] = discover_repositories(
        tuple(draft.search_roots), draft.max_depth
    )
    paths = [candidate.canonical_path for candidate in discovered]
    paths.extend(
        canonical
        for canonical in (canonicalize(path) for path in draft.selected)
        if canonical not in paths
    )
    return paths


def _flip(values: list, value: object) -> None:
    if value in values:
        values.remove(value)
    else:
        values.append(value)


def _ordered(values: list, order: tuple) -> tuple:
    return tuple(name for name in order if name in values)


def _build(draft: _Draft) -> DesiredState:
    return DesiredState(
        harnesses=_ordered(draft.harnesses, HARNESS_NAMES),
        components=_ordered(draft.components, COMPONENT_NAMES),
        repositories=RepositorySelection(
            search_roots=tuple(draft.search_roots),
            max_depth=draft.max_depth,
            selected=tuple(sorted(draft.selected)),
        ),
    )
