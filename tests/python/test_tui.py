"""Tests for the linear install wizard (``cheese_flow.tui``).

The wizard is driven end to end with scripted stdin: one line per prompt. An
empty line accepts the screen, digits toggle entries, ``b`` goes back, and ``q``
cancels. Detection and repository discovery are the wizard's inputs, so they are
substituted; the prompt flow itself is never faked.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from cheese_flow import tui
from cheese_flow.models import (
    DesiredState,
    RepositoryCandidate,
    RepositorySelection,
)

SCREEN_HEADERS = (
    "[1/6] Preflight",
    "[2/6] Harnesses",
    "[3/6] Components",
    "[4/6] Search roots",
    "[5/6] Repository candidates",
    "[6/6] Preview",
)


def candidate(path: str) -> RepositoryCandidate:
    resolved = Path(path)
    return RepositoryCandidate(
        canonical_path=resolved,
        name=resolved.name,
        main_worktree=resolved,
        writable=True,
    )


CANDIDATES = (candidate("/srv/code/alpha"), candidate("/srv/code/beta"))


class Discovery:
    """Records the arguments the wizard discovers repositories with."""

    def __init__(self, found: tuple[RepositoryCandidate, ...] = CANDIDATES) -> None:
        self.found = found
        self.calls: list[tuple[tuple[Path, ...], int]] = []

    def __call__(self, roots: tuple[Path, ...], max_depth: int) -> tuple[RepositoryCandidate, ...]:
        self.calls.append((roots, max_depth))
        return self.found


@pytest.fixture
def wizard(monkeypatch: pytest.MonkeyPatch):
    """Return a ``run(script, initial=None)`` driver over a scripted stdin."""
    discovery = Discovery()
    detected: list[str] = ["claude-code", "codex"]
    monkeypatch.setattr(tui, "discover_repositories", discovery)
    monkeypatch.setattr(tui, "detect_available_harnesses", lambda: tuple(detected))

    def run(script: list[str], initial: DesiredState | None = None) -> DesiredState | None:
        monkeypatch.setattr("sys.stdin", io.StringIO("".join(f"{line}\n" for line in script)))
        return tui.run_wizard(initial)

    run.discovery = discovery  # type: ignore[attr-defined]
    run.detected = detected  # type: ignore[attr-defined]
    return run


ACCEPT_ALL = ["", "", "", "/srv/code", "", "", ""]


# ─── Defaults ────────────────────────────────────────────────────────────────


def test_detected_harnesses_start_selected(wizard) -> None:
    state = wizard(ACCEPT_ALL)

    assert state is not None
    assert state.harnesses == ("claude-code", "codex")


def test_tilth_and_repository_candidates_start_unchecked(wizard) -> None:
    state = wizard(ACCEPT_ALL)

    assert state is not None
    assert state.components == ("hallouminate", "easy-cheese")
    assert state.repositories.selected == ()


def test_undetected_harness_can_be_selected(wizard) -> None:
    # Harness list is [1] claude-code, [2] codex, [3] cursor.
    state = wizard(["", "3", "", "", "/srv/code", "", "", ""])

    assert state is not None
    assert state.harnesses == ("claude-code", "codex", "cursor")


def test_tilth_can_be_selected(wizard) -> None:
    # Component list is [1] hallouminate, [2] easy-cheese, [3] tilth.
    state = wizard(["", "", "3", "", "/srv/code", "", "", ""])

    assert state is not None
    assert state.components == ("hallouminate", "easy-cheese", "tilth")


def test_repository_candidates_can_be_selected(wizard) -> None:
    state = wizard(["", "", "", "/srv/code", "", "1 2", "", ""])

    assert state is not None
    assert state.repositories.selected == (Path("/srv/code/alpha"), Path("/srv/code/beta"))


def test_search_roots_and_depth_drive_discovery(wizard) -> None:
    state = wizard(["", "", "", "/srv/code, /opt/src", "3", "", ""])

    assert state is not None
    assert state.repositories.search_roots == (Path("/srv/code"), Path("/opt/src"))
    assert state.repositories.max_depth == 3
    assert wizard.discovery.calls == [((Path("/srv/code"), Path("/opt/src")), 3)]


# ─── Required components (spec:87) ───────────────────────────────────────────


def test_required_components_cannot_be_deselected(wizard, capsys) -> None:
    state = wizard(["", "", "1", "2", "", "/srv/code", "", "", ""])

    assert state is not None
    assert state.components == ("hallouminate", "easy-cheese")
    stderr = capsys.readouterr().err
    assert "hallouminate is required" in stderr
    assert "easy-cheese is required" in stderr


def test_deselecting_every_harness_is_rejected_and_reprompts(wizard, capsys) -> None:
    state = wizard(["", "1 2", "", "1", "", "", "/srv/code", "", "", ""])

    assert state is not None
    assert state.harnesses == ("claude-code",)
    assert "at least one harness" in capsys.readouterr().err


def test_relative_search_root_is_rejected_and_reprompts(wizard, capsys) -> None:
    state = wizard(["", "", "", "relative/path", "/srv/code", "", "", ""])

    assert state is not None
    assert state.repositories.search_roots == (Path("/srv/code"),)
    assert "must be absolute" in capsys.readouterr().err


# ─── Prefill (spec:87) ───────────────────────────────────────────────────────


def existing_state() -> DesiredState:
    return DesiredState(
        harnesses=("claude-code", "cursor"),
        components=("hallouminate", "easy-cheese", "tilth"),
        repositories=RepositorySelection(
            search_roots=(Path("/srv/code"),),
            max_depth=4,
            selected=(Path("/srv/code/alpha"),),
        ),
    )


def test_existing_manifest_prefills_every_screen_and_survives_accepting_each(wizard) -> None:
    initial = existing_state()

    state = wizard(["", "", "", "", "", "", ""], initial)

    assert state == initial


def test_existing_manifest_skips_no_screen(wizard, capsys) -> None:
    wizard(["", "", "", "", "", "", ""], existing_state())

    stderr = capsys.readouterr().err
    positions = [stderr.find(header) for header in SCREEN_HEADERS]
    assert all(position >= 0 for position in positions), f"missing screen: {positions}"
    assert positions == sorted(positions)


def test_prefilled_selection_survives_discovery_that_no_longer_finds_it(
    monkeypatch: pytest.MonkeyPatch, wizard
) -> None:
    monkeypatch.setattr(tui, "discover_repositories", Discovery(found=()))

    state = wizard(["", "", "", "", "", "", ""], existing_state())

    assert state is not None
    assert state.repositories.selected == (Path("/srv/code/alpha"),)


def test_prefilled_repository_can_be_deselected(wizard) -> None:
    state = wizard(["", "", "", "", "", "1 2", "", ""], existing_state())

    assert state is not None
    assert state.repositories.selected == (Path("/srv/code/beta"),)


# ─── Back before Apply (spec:87) ─────────────────────────────────────────────


def test_back_from_preview_reopens_the_repository_screen(wizard, capsys) -> None:
    state = wizard(["", "", "", "/srv/code", "", "", "b", "1", "", ""])

    assert state is not None
    assert state.repositories.selected == (Path("/srv/code/alpha"),)
    assert capsys.readouterr().err.count("[5/6] Repository candidates") == 2


def test_back_walks_all_the_way_to_the_harness_screen(wizard, capsys) -> None:
    # repos -> back -> search roots -> back -> components -> back -> harnesses.
    script = ["", "", "", "/srv/code", "", "b", "b", "b", "3", "", "", "", "", "", ""]
    state = wizard(script)

    assert state is not None
    assert state.harnesses == ("claude-code", "codex", "cursor")
    assert capsys.readouterr().err.count("[2/6] Harnesses") == 2


# ─── Cancellation (acceptance:146) ───────────────────────────────────────────


def test_quit_at_preview_returns_none(wizard) -> None:
    assert wizard(["", "", "", "/srv/code", "", "", "q"]) is None


def test_quit_at_the_first_screen_returns_none(wizard) -> None:
    assert wizard(["q"]) is None


def test_end_of_input_cancels(wizard) -> None:
    assert wizard([]) is None


# ─── Output discipline (spec:125) ────────────────────────────────────────────


def test_wizard_writes_nothing_to_stdout(wizard, capsys) -> None:
    state = wizard(ACCEPT_ALL)

    assert state is not None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[6/6] Preview" in captured.err
