"""Port of ``tests/cook-flow.test.ts`` — assertions on shipped /cook artifacts."""

from __future__ import annotations

import re
from pathlib import Path

from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.schemas import (
    parse_agent_frontmatter,
    parse_command_frontmatter,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_ships_focused_cook_command_without_batching_or_fleet_language() -> None:
    source = _read("commands/cook.md")
    data, body = parse_frontmatter(source)
    command = parse_command_frontmatter(data)

    assert command.name == "cook"
    assert "cut → cook → taste-test → press" in body
    assert "Cheez skills" in body
    assert not re.search(r"\b(batch|batching|fleet|parallel worktree)\b", body, re.IGNORECASE)
    assert not re.search(r"\bfromage\b", body, re.IGNORECASE)


def test_binds_cook_flow_agents_to_the_cheez_skills() -> None:
    for agent in (
        "cut",
        "cook",
        "press",
        "assertion-review",
        "taste-spec",
        "taste-readability",
        "taste-scope",
    ):
        source = _read(f"agents/{agent}.md.eta")
        data, body = parse_frontmatter(source)
        frontmatter = parse_agent_frontmatter(data)

        assert "cheez-read" in frontmatter.skills
        assert "cheez-search" in frontmatter.skills
        assert "test-driven-development" not in frontmatter.skills
        assert "Self-evaluation checklist" in body


def test_inlines_tdd_core_rule_in_cut_and_cook_agent_bodies() -> None:
    cut = _read("agents/cut.md.eta")
    assert "No production code without a failing test first" in cut
    cook = _read("agents/cook.md.eta")
    assert "Red → Green → Refactor" in cook


def test_declares_assertion_review_as_spec_drift_detector_with_scoring_rubric() -> None:
    source = _read("agents/assertion-review.md.eta")
    data, body = parse_frontmatter(source)
    frontmatter = parse_agent_frontmatter(data)
    assert frontmatter.name == "assertion-review"
    assert "Spec-drift rubric" in body
    assert "STRONG" in body
    assert "MISSING" in body
    assert "CONTRADICTS" in body


def test_runs_taste_test_as_two_round_cook_feedback_loop() -> None:
    source = _read("commands/cook.md")
    assert "cook → taste-test → cook → taste-test → cook" in source
    assert "hard two-round taste-test limit" in source
    assert "taste-spec" in source
    assert "taste-readability" in source
    assert "taste-scope" in source


def test_wires_cook_into_cheese_routing_table() -> None:
    source = _read("commands/cheese.md")
    assert "`/cook`" in source
    assert not re.search(r"`/fromage`", source)
